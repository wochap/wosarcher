"""`wosarcher run` with the real adapters against recorded SearXNG, Firecrawl, and LLM responses."""

import json
import os
import re
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from tests.fixtures import recorded
from tests.fixtures.recorded import NOTES, QUERY, config_home, recorded_router
from wosarcher.cli import app
from wosarcher.config import resolve
from wosarcher.models import Context, Plan, ResearchRecord, RunOutput, parse_event
from wosarcher.store import STAGE_ARTIFACTS

runner = CliRunner()
RUN_ID = "20260101-120000-e2e000"


@pytest.fixture
def runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("WOSARCHER_PROFILE", "WOSARCHER_SCORE__API_KEY", "WOSARCHER_LLM__API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home(tmp_path / "config")))
    monkeypatch.setenv("WOSARCHER_RUN__RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("WOSARCHER_RUN__CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path / "runs"


def test_profile_resolves(runs: Path) -> None:
    settings = resolve("e2e", [], os.environ)
    assert (settings.search.base_url, settings.fetch.base_url) == ("http://searxng.test", "http://firecrawl.test/v1")
    assert (settings.llm.base_url, settings.prefilter.provider, settings.score.provider) == (
        "http://llm.test/v1",
        "bm25",
        "bm25",
    )


async def test_router_answers_recorded_requests() -> None:
    with recorded_router():
        async with httpx.AsyncClient() as http:
            found = await http.get("http://searxng.test/search", params={"q": QUERY, "format": "json"})
            missing = await http.post("http://firecrawl.test/v1/scrape", json={"url": "https://nowhere.test/page"})
            assert found.json()["results"][0]["url"] == "https://en.wikipedia.org/wiki/Battery_recycling"
            assert missing.status_code == 404
            with pytest.raises(respx.models.AllMockedAssertionError, match=r"https://other\.test/x"):
                await http.get("https://other.test/x")


def test_full_run(runs: Path) -> None:
    with recorded_router():
        result = runner.invoke(app, ["run", QUERY, "--profile", "e2e", "--attach", str(NOTES), "--run-id", RUN_ID])
    assert result.exit_code == 0, result.output
    run_dir = runs / RUN_ID
    events = [parse_event(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    assert events[-1].type == "run.done"
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert any(event.type == "page.failed" for event in events)
    expected = [name for names in STAGE_ARTIFACTS.values() for name in names if name != "research.json"]
    for name in [*expected, "request.json", "costs.json", "attachments/notes.md"]:
        assert (run_dir / name).is_file(), name
    context = Context.model_validate_json((run_dir / "context.json").read_text())
    numbers = {passage.n for passage in context.passages}
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", (run_dir / "report.md").read_text())}
    assert cited
    assert cited <= numbers


def test_until_select_json(runs: Path) -> None:
    with recorded_router():
        result = runner.invoke(app, ["run", QUERY, "--profile", "e2e", "--until", "select", "--json"])
    assert result.exit_code == 0, result.output
    output = RunOutput.model_validate(json.loads(result.stdout))
    assert output.report is None
    assert output.context is not None
    assert output.context.passages


def test_quick_depth(runs: Path) -> None:
    with recorded_router():
        result = runner.invoke(app, ["run", QUERY, "--profile", "e2e", "--depth", "quick", "--run-id", RUN_ID])
    assert result.exit_code == 0, result.output
    run_dir = runs / RUN_ID
    record = json.loads((run_dir / "request.json").read_text())
    assert record["request"]["depth"] == "quick"
    assert record["settings"]["fetch"]["max_pages"] == 15
    events = [parse_event(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    assert len([event for event in events if event.type == "page.fetched"]) <= 15
    listed = runner.invoke(app, ["runs", "--json"])
    assert json.loads(listed.stdout)[0]["depth"] == "quick"


FOLLOW_UP = "battery recycling regulation deadlines"
REGULATION_URL = "https://regulations.example.org/battery-rules"
REGULATION_PAGE = (
    "# Battery regulation\n\nThe battery recycling regulation sets deadlines: recycling efficiency targets for "
    "lithium batteries rise in 2027 and 2031, with regulation deadlines for material recovery."
)


def completion(content: str) -> httpx.Response:
    choice = {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
    return httpx.Response(200, json={"id": "c", "object": "chat.completion", "choices": [choice]})


def deep_router() -> respx.MockRouter:
    """The recorded world plus one follow-up search and page; the gap step continues once, then stops."""
    gaps: list[dict[str, object]] = [
        {"queries": [FOLLOW_UP], "note": "Regulation is missing.", "stop": False},
        {"queries": [], "note": "Methods, economics, and regulation are covered.", "stop": True},
    ]

    def search(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("q") == FOLLOW_UP:
            result = {"url": REGULATION_URL, "title": "Battery regulation", "content": "Deadlines."}
            return httpx.Response(200, json={"results": [result]})
        return recorded.search(request)

    def scrape(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["url"] == REGULATION_URL:
            data = {"markdown": REGULATION_PAGE, "metadata": {"title": "Battery regulation", "statusCode": 200}}
            return httpx.Response(200, json={"success": True, "data": data})
        return recorded.scrape(request)

    def chat(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        if "You review web research" in system:
            return completion(json.dumps(gaps.pop(0)))
        if body.get("stream"):
            numbers = re.findall(r"^\[(\d+)\] ", body["messages"][1]["content"], re.MULTILINE)
            text = "Battery recycling is regulated " + "".join(f"[{n}]" for n in numbers) + "."
            chunk = {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": "stop"}]}
            return httpx.Response(200, content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode())
        return recorded.chat(request)

    router = respx.mock(assert_all_mocked=True, assert_all_called=False)
    router.get("http://searxng.test/search").mock(side_effect=search)
    router.post("http://firecrawl.test/v1/scrape").mock(side_effect=scrape)
    router.post("http://llm.test/v1/chat/completions").mock(side_effect=chat)
    return router


def test_deep_run_two_rounds(runs: Path) -> None:
    with deep_router():
        result = runner.invoke(app, ["run", QUERY, "--profile", "e2e", "--depth", "deep", "--run-id", RUN_ID])
    assert result.exit_code == 0, result.output
    run_dir = runs / RUN_ID
    research = ResearchRecord.model_validate_json((run_dir / "research.json").read_text())
    assert (research.planned, research.ran, research.reason) == (3, 2, "model judged coverage sufficient")
    assert research.note == "Methods, economics, and regulation are covered."
    plan = Plan.model_validate_json((run_dir / "plan.json").read_text())
    rounds = {query.id: query.round for query in plan.queries}
    context = Context.model_validate_json((run_dir / "context.json").read_text())
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", (run_dir / "report.md").read_text())}
    cited_rounds = {rounds[passage.query_id] for passage in context.passages if passage.n in cited}
    assert cited_rounds == {1, 2}
    listed = json.loads(runner.invoke(app, ["runs", "--json"]).stdout)
    assert (listed[0]["rounds_planned"], listed[0]["rounds_ran"]) == (3, 2)


BRIEF = (
    "I am preparing a briefing for a regional council on battery recycling. Cover how lithium-ion batteries are "
    "collected and sorted, which recycling methods exist (pyrometallurgy, hydrometallurgy, direct recycling) and "
    "how their recovery rates compare, what the economics of a recycling plant look like per tonne, which "
    "regulations and recycling efficiency targets apply in the coming years, and what safety hazards come up "
    "during transport and storage. Close with recommendations for a mid-sized city."
)


def traced_router(calls: list[tuple[str, str]]) -> respx.MockRouter:
    """The recorded world; every search query and LLM request body is appended to `calls` in order."""

    def search(request: httpx.Request) -> httpx.Response:
        calls.append(("search", request.url.params.get("q", "")))
        return recorded.search(request)

    def chat(request: httpx.Request) -> httpx.Response:
        calls.append(("chat", request.content.decode()))
        return recorded.chat(request)

    router = respx.mock(assert_all_mocked=True, assert_all_called=False)
    router.get("http://searxng.test/search").mock(side_effect=search)
    router.post("http://firecrawl.test/v1/scrape").mock(side_effect=recorded.scrape)
    router.post("http://llm.test/v1/chat/completions").mock(side_effect=chat)
    return router


def test_long_brief_searches_the_topic(runs: Path) -> None:
    calls: list[tuple[str, str]] = []
    with traced_router(calls):
        result = runner.invoke(app, ["run", BRIEF, "--profile", "e2e", "--sources", "web", "--run-id", RUN_ID])
    assert result.exit_code == 0, result.output
    run_dir = runs / RUN_ID
    assert len(BRIEF) > 200
    assert calls[0][0] == "chat"
    assert (run_dir / "initial.jsonl").read_text() == ""
    plan = Plan.model_validate_json((run_dir / "plan.json").read_text())
    assert (plan.queries[0].id, plan.queries[0].text, plan.warnings) == ("q0", QUERY, [])
    searched = [text for kind, text in calls if kind == "search"]
    assert sorted(searched) == sorted(query.text for query in plan.queries)
    assert all(len(text) <= 200 for text in searched)
    bodies = [json.loads(body) for kind, body in calls if kind == "chat"]
    writer = next(body for body in bodies if body.get("stream"))
    assert any(BRIEF in message["content"] for message in writer["messages"])


def test_short_query_searched_before_planning(runs: Path) -> None:
    calls: list[tuple[str, str]] = []
    with traced_router(calls):
        result = runner.invoke(app, ["run", QUERY, "--profile", "e2e", "--sources", "web", "--run-id", RUN_ID])
    assert result.exit_code == 0, result.output
    assert calls[0] == ("search", QUERY)
    planner = json.loads(calls[1][1])
    assert calls[1][0] == "chat"
    assert "Battery recycling - Wikipedia" in planner["messages"][1]["content"]
    searched = [text for kind, text in calls if kind == "search"]
    assert searched.count(QUERY) == 1

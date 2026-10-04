"""`wosarcher run` with the real adapters against recorded SearXNG, Firecrawl, and LLM responses."""

import json
import os
import re
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from tests.fixtures.recorded import NOTES, QUERY, config_home, recorded_router
from wosarcher.cli import app
from wosarcher.config import resolve
from wosarcher.models import Context, RunOutput, parse_event
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
    expected = [name for names in STAGE_ARTIFACTS.values() for name in names]
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

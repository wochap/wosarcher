import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from wosarcher.daemon import app

runner = CliRunner()
ENTRIES = {
    "search/searxng": 'provider = "searxng"\nbase_url = "http://searx.test"\n',
    "fetch/firecrawl": 'provider = "firecrawl"\nbase_url = "http://crawl.test/v1"\n',
    "score/rerank": (
        'provider = "rerank"\nbase_url = "http://rerank.test/v1"\nfallback_urls = ["http://rerank-backup.test/v1"]\n'
    ),
    "llm/writer": 'provider = "openai"\nbase_url = "http://llm.test/v1"\nmodel = "writer"\n',
}
PROFILE = '[use]\nprefilter = "bm25"\nscore = "rerank"\nllm = "writer"\n'


def write_entry(config_home: Path, name: str, text: str) -> None:
    path = config_home / "wosarcher" / "providers" / f"{name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture(autouse=True)
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)
    profiles = tmp_path / "wosarcher" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "test.toml").write_text(PROFILE)
    for name, text in ENTRIES.items():
        write_entry(tmp_path, name, text)
    return tmp_path


def hosts() -> set[str]:
    requests: list[httpx.Request] = [call.request for call in respx.calls]  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    return {request.url.host for request in requests}


def healthy_routes() -> None:
    respx.get("http://searx.test/search").respond(200, json={"results": []})
    scraped = {"success": True, "data": {"markdown": "Example", "metadata": {"title": "Example"}}}
    respx.post("http://crawl.test/v1/scrape").respond(200, json=scraped)
    respx.post("http://rerank.test/v1/rerank").respond(200, json={"results": [{"index": 0, "relevance_score": 1}]})
    reply = {"model": "qwen3-8b-q4_k_m", "choices": [{"message": {"content": "OK"}}]}
    respx.post("http://llm.test/v1/chat/completions", name="llm").respond(200, json=reply)
    respx.get("http://llm.test/props").respond(404)
    respx.get(url__regex=r"^http://llm.test/upstream/.*/props$").respond(404)
    respx.get("http://llm.test/v1/models").respond(404)


@respx.mock
def test_doctor_all_ok_exit_0() -> None:
    healthy_routes()
    result = runner.invoke(app, ["doctor", "--profile", "test"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "qwen3-8b-q4_k_m" in result.output
    assert "built in" in result.output


@respx.mock
def test_doctor_failure_exit_1() -> None:
    healthy_routes()
    respx.post("http://rerank.test/v1/rerank").mock(side_effect=httpx.ConnectError("refused"))
    respx.post("http://rerank-backup.test/v1/rerank").mock(side_effect=httpx.ConnectError("refused"))
    result = runner.invoke(app, ["doctor", "--profile", "test", "--json"])
    assert result.exit_code == 1
    rows = {row["block"]: row for row in json.loads(result.output)["providers"]}
    assert rows["score"]["status"] == "failed"
    assert "http://rerank-backup.test/v1/rerank" in rows["score"]["error"]
    assert rows["llm"]["status"] == "ok"


@respx.mock
def test_doctor_other_profile(config_home: Path) -> None:
    healthy_routes()
    write_entry(config_home, "llm/far", 'provider = "openai"\nbase_url = "http://far.test/v1"\n')
    (config_home / "wosarcher" / "profiles" / "workstation.toml").write_text(PROFILE.replace("writer", "far"))
    assert runner.invoke(app, ["profile", "use", "workstation"]).exit_code == 0
    result = runner.invoke(app, ["doctor", "--profile", "test", "--set", "llm.model=other", "--json"])
    assert result.exit_code == 0, result.output
    assert (
        respx.calls.call_count == 7
    )  # with two props and models; unmatched hosts (the workstation profile's far.test) would raise
    assert json.loads(respx.routes["llm"].calls.last.request.content)["model"] == "other"


@respx.mock
def test_doctor_models_note() -> None:
    healthy_routes()
    respx.get("http://llm.test/v1/models").respond(200, json={"data": [{"id": f"m{n}"} for n in range(12)]})
    result = runner.invoke(app, ["doctor", "--profile", "test", "--json"])
    assert result.exit_code == 0, result.output
    rows = {row["block"]: row for row in json.loads(result.output)["providers"]}
    assert "12 models listed" in rows["llm"]["note"]


@respx.mock
def test_doctor_no_models_endpoint() -> None:
    healthy_routes()
    result = runner.invoke(app, ["doctor", "--profile", "test", "--json"])
    assert result.exit_code == 0, result.output
    rows = {row["block"]: row for row in json.loads(result.output)["providers"]}
    assert rows["llm"]["note"] is None


@respx.mock
def test_doctor_json() -> None:
    healthy_routes()
    result = runner.invoke(app, ["doctor", "--profile", "test", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert [row["block"] for row in report["providers"]] == ["search", "fetch", "prefilter", "score", "llm"]
    assert report["providers"][2]["status"] == "built-in"
    assert report["warnings"] == []


@respx.mock
def test_doctor_context_warning_keeps_exit_0() -> None:
    healthy_routes()
    respx.get("http://llm.test/props").respond(200, json={"default_generation_settings": {"n_ctx": 4096}})
    result = runner.invoke(app, ["doctor", "--profile", "test"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "llm/writer: server context 4096 tokens" in result.output
    assert "below llm.context_window = 32768" in result.output


@respx.mock
def test_doctor_json_reports_release_and_gpu_policy(config_home: Path) -> None:
    healthy_routes()
    write_entry(config_home, "prefilter/kw", 'provider = "bm25"\nrelease = "llama-swap"\n')
    text = PROFILE.replace('prefilter = "bm25"', 'prefilter = "kw"')
    (config_home / "wosarcher" / "profiles" / "exclusive.toml").write_text(text + '\n[run]\ngpu_policy = "exclusive"\n')
    result = runner.invoke(app, ["doctor", "--profile", "exclusive", "--json"])
    report = json.loads(result.output)
    assert report["gpu_policy"] == "exclusive"
    releases = {row["block"]: row["release"] for row in report["providers"]}
    assert releases == {"search": "none", "fetch": "none", "prefilter": "llama-swap", "score": "none", "llm": "none"}


@respx.mock
def test_doctor_one_block() -> None:
    healthy_routes()
    result = runner.invoke(app, ["doctor", "--profile", "test", "--block", "score", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert [row["block"] for row in report["providers"]] == ["score"]
    assert respx.calls.call_count == 1
    assert respx.calls.last.request.url.host == "rerank.test"


@respx.mock
def test_doctor_unknown_block() -> None:
    result = runner.invoke(app, ["doctor", "--profile", "test", "--block", "scorer"])
    assert result.exit_code != 0
    for name in ("search", "fetch", "prefilter", "score", "llm"):
        assert name in result.output
    assert not respx.calls


@respx.mock
def test_doctor_another_entry(config_home: Path) -> None:
    write_entry(config_home, "llm/agents", 'provider = "openai"\nbase_url = "http://agents.test/v1"\nmodel = "a"\n')
    respx.post("http://agents.test/v1/chat/completions").respond(
        200, json={"choices": [{"message": {"content": "OK"}}]}
    )
    respx.get(url__regex=r"^http://agents.test/.*").respond(404)
    result = runner.invoke(app, ["doctor", "--profile", "test", "--use", "llm=agents", "--block", "llm", "--json"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)["providers"]
    assert [(row["block"], row["entry"]) for row in rows] == [("llm", "agents")]
    assert hosts() == {"agents.test"}


@respx.mock
def test_doctor_entries_mode(config_home: Path) -> None:
    write_entry(config_home, "score/jev-strict", 'provider = "jev"\nbase_url = "http://jev.test/v1"\napi_key = "k"\n')
    respx.post("http://rerank.test/v1/rerank").respond(200, json={"results": [{"index": 0, "relevance_score": 1}]})
    respx.post(url__regex=r"^http://jev.test/.*").respond(200, json={"results": [{"index": 0, "score": 3}]})
    args = ["doctor", "--entry", "score=jev-strict", "--entry", "score=rerank", "--json"]
    result = runner.invoke(app, args)
    rows = json.loads(result.output)["providers"]
    assert [(row["block"], row["entry"]) for row in rows] == [("score", "jev-strict"), ("score", "rerank")]
    assert hosts() == {"jev.test", "rerank.test"}


def test_doctor_entries_mode_unknown_entry() -> None:
    result = runner.invoke(app, ["doctor", "--entry", "score=nope"], env={"COLUMNS": "200"})
    assert result.exit_code == 1
    assert "unknown score entry 'nope'; score entries: bm25, rerank" in result.output

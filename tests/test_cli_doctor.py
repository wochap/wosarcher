import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from wosarcher.cli import app

runner = CliRunner()
PROFILE = """
[search]
provider = "searxng"
base_url = "http://searx.test"

[fetch]
provider = "firecrawl"
base_url = "http://crawl.test/v1"

[prefilter]
provider = "bm25"

[score]
provider = "rerank"
base_url = "http://rerank.test/v1"
fallback_urls = ["http://rerank-backup.test/v1"]

[llm]
provider = "llm"
base_url = "http://llm.test/v1"
model = "writer"
"""


@pytest.fixture(autouse=True)
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)
    profiles = tmp_path / "wosarcher" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "test.toml").write_text(PROFILE)
    return tmp_path


def healthy_routes() -> None:
    respx.get("http://searx.test/search").respond(200, json={"results": []})
    scraped = {"success": True, "data": {"markdown": "Example", "metadata": {"title": "Example"}}}
    respx.post("http://crawl.test/v1/scrape").respond(200, json=scraped)
    respx.post("http://rerank.test/v1/rerank").respond(200, json={"results": [{"index": 0, "relevance_score": 1}]})
    reply = {"model": "qwen3-8b-q4_k_m", "choices": [{"message": {"content": "OK"}}]}
    respx.post("http://llm.test/v1/chat/completions", name="llm").respond(200, json=reply)
    respx.get("http://llm.test/props").respond(404)
    respx.get(url__regex=r"^http://llm.test/upstream/.*/props$").respond(404)


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
def test_doctor_other_profile() -> None:
    healthy_routes()
    assert runner.invoke(app, ["profile", "use", "workstation"]).exit_code == 0
    result = runner.invoke(app, ["doctor", "--profile", "test", "--set", "llm.model=other", "--json"])
    assert result.exit_code == 0, result.output
    assert respx.calls.call_count == 6  # with two props; unmatched hosts (the workstation profile) would raise
    assert json.loads(respx.routes["llm"].calls.last.request.content)["model"] == "other"


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
    assert "llm: server context 4096 tokens" in result.output
    assert "below llm.context_window = 32768" in result.output

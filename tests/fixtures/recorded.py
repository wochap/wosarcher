"""Recorded SearXNG, Firecrawl, and LLM responses as a respx router, plus the `e2e` profile.

Shared by the end-to-end test, the eval tests, and `make_recorded_run.py`.
"""

import json
import re
import shutil
from pathlib import Path

import httpx
import respx

FIXTURES = Path(__file__).resolve().parent
HTTP = FIXTURES / "http"
NOTES = HTTP / "notes.md"
PROFILE = FIXTURES / "profiles" / "e2e.toml"
RUNS = FIXTURES / "runs"
FIXTURE_RUN = "20260101-000000-fixture"
QUERY = "battery recycling"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def config_home(target: Path) -> Path:
    """An `XDG_CONFIG_HOME` under `target` whose only user profile is `e2e`."""
    profiles = target / "wosarcher" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROFILE, profiles / PROFILE.name)
    return target


def search(request: httpx.Request) -> httpx.Response:
    path = HTTP / "searxng" / f"{slug(request.url.params.get('q', ''))}.json"
    body: object = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"results": []}
    return httpx.Response(200, json=body)


def scrape(request: httpx.Request) -> httpx.Response:
    path = HTTP / "firecrawl" / f"{slug(json.loads(request.content)['url'])}.json"
    if not path.is_file():
        return httpx.Response(404, json={"success": False, "error": "not found"})
    return httpx.Response(200, content=path.read_bytes(), headers={"content-type": "application/json"})


def chat(request: httpx.Request) -> httpx.Response:
    if json.loads(request.content).get("stream"):
        body = (HTTP / "llm" / "write.sse").read_bytes()
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})
    return httpx.Response(200, content=(HTTP / "llm" / "plan.json").read_bytes())


def recorded_router() -> respx.MockRouter:
    """Answers the `*.test` hosts of the `e2e` profile; any other request raises `AllMockedAssertionError`."""
    router = respx.mock(assert_all_mocked=True, assert_all_called=False)
    router.get("http://searxng.test/search").mock(side_effect=search)
    router.post("http://firecrawl.test/v1/scrape").mock(side_effect=scrape)
    router.post("http://llm.test/v1/chat/completions").mock(side_effect=chat)
    return router


def copy_fixture(runs_dir: Path) -> str:
    """Copy the committed fixture run into `runs_dir`; return its run ID."""
    shutil.copytree(RUNS / FIXTURE_RUN, runs_dir / FIXTURE_RUN)
    return FIXTURE_RUN

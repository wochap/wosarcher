"""A small fake world for runner and CLI tests: settings, fake adapters, and a run directory."""

from collections.abc import Mapping
from pathlib import Path

from wosarcher.adapters.fakes import FakeEmbedder, FakeFetcher, FakeLLM, FakeManaged, FakeSearcher, healthy
from wosarcher.config import RunConfig, Settings
from wosarcher.models import Event, RunRequest, Sources, Stage
from wosarcher.ports import LLM, Adapters, Embedder, Fetcher, Managed, Scorer, Searcher
from wosarcher.store import RunStore

QUERY = "battery recycling"
SEARCH = {
    QUERY: ["https://a.test/x", "https://b.test"],
    "recycling cost": ["https://c.test"],
}
PAGES = {
    "https://a.test/x": "# Overview\nLithium recovery rates from battery recycling plants.",
    "https://b.test": "# Costs\nBattery recycling plant costs per tonne.",
    "https://c.test": "Recycling cost estimates for batteries.",
}
PLAN_REPLY = '{"topic": "battery recycling", "queries": ["recycling cost"], "parts": ["cost", "methods"]}'
REPORT_REPLY = "Battery recycling recovers lithium [1]."


def settings(tmp_path: Path, **run: object) -> Settings:
    return Settings(
        run=RunConfig.model_validate({"runs_dir": tmp_path / "runs", "cache_dir": tmp_path / "cache", **run})
    )


def adapters(
    *,
    searcher: Searcher | None = None,
    fetcher: Fetcher | None = None,
    planner: LLM | None = None,
    gapper: LLM | None = None,
    writer: LLM | None = None,
    scorers: dict[str, Scorer] | None = None,
    embedder: Embedder | None = None,
    managed: Mapping[str, Managed] | None = None,
) -> Adapters:
    """`gapper` defaults to the planner, so one script holds the plan and gap replies."""
    planner = planner or FakeLLM([PLAN_REPLY])
    return Adapters(
        searcher=searcher or FakeSearcher(SEARCH),
        fetcher=fetcher or FakeFetcher(PAGES),
        embedder=embedder or FakeEmbedder(),
        scorers=scorers or {},
        planner=planner,
        gapper=gapper or planner,
        writer=writer or FakeLLM([REPORT_REPLY]),
        managed=dict(managed or {}),
    )


def new_run(
    store: RunStore,
    cfg: Settings,
    *,
    sources: Sources = "both",
    until: Stage | None = None,
    attachments: list[str] | None = None,
    query: str = QUERY,
) -> str:
    request = RunRequest(query=query, sources=sources, until=until)
    return store.create(request, "workstation", [], cfg, attachments or []).run_id


def kinds(events: list[Event]) -> list[str]:
    return [event.type + (f":{event.stage}" if event.stage else "") for event in events]


class Releases(FakeManaged):
    """A Managed whose releases are recorded in a shared list."""

    def __init__(self, name: str, log: list[str]) -> None:
        super().__init__(healthy(name, "fake"))
        self.name = name
        self.log = log

    async def release(self) -> None:
        self.log.append(self.name)

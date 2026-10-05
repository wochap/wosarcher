"""The research loop with fakes: rounds, stop rules, pairing across rounds, usage, resume, and fork."""

import asyncio
import json
from pathlib import Path

import pytest

from tests.runner.helpers import PAGES, PLAN_REPLY, QUERY, SEARCH, adapters, kinds, new_run, settings
from wosarcher.adapters.fakes import FakeFetcher, FakeLLM, FakeScorer, FakeSearcher
from wosarcher.config import FetchConfig, ResearchConfig, ScoreConfig, SelectConfig, Settings
from wosarcher.http import UsageLedger
from wosarcher.models import (
    Candidate,
    Chunk,
    Completion,
    GapReady,
    Message,
    Page,
    Plan,
    Query,
    ResearchDone,
    ResearchRecord,
    RoundDone,
    Score,
    StageDone,
    StageStarted,
)
from wosarcher.ports import Adapters, Scorer
from wosarcher.runner import Runner
from wosarcher.runner.steps import gap_budget, round_cap
from wosarcher.store import RunStore

WORLD = {
    **SEARCH,
    "lithium price": ["https://d.test"],
    "cobalt supply": ["https://e.test"],
    "again": ["https://a.test/x"],
}
PAGES_ALL = {**PAGES, "https://d.test": "Lithium price per tonne in 2026.", "https://e.test": "Cobalt supply chains."}


def gap_reply(*queries: str, stop: bool = False, note: str = "More on prices.") -> str:
    return json.dumps({"queries": list(queries), "note": note, "stop": stop})


def configured(tmp_path: Path, rounds: int = 3, **update: object) -> Settings:
    cfg = settings(tmp_path)
    return cfg.model_copy(update={"research": ResearchConfig(rounds=rounds), **update})


def world(
    *gaps: str,
    searcher: FakeSearcher | None = None,
    fetcher: FakeFetcher | None = None,
    scorers: dict[str, Scorer] | None = None,
) -> Adapters:
    return adapters(
        searcher=searcher or FakeSearcher(WORLD),
        fetcher=fetcher or FakeFetcher(PAGES_ALL),
        planner=FakeLLM([PLAN_REPLY, *gaps]),
        scorers=scorers,
    )


def planner_of(fakes: Adapters) -> FakeLLM:
    assert isinstance(fakes.planner, FakeLLM)
    return fakes.planner


async def run(cfg: Settings, run_id: str, fakes: Adapters, ledger: UsageLedger | None = None) -> str:
    store = RunStore.from_settings(cfg)
    return await Runner(store, cfg, fakes, ledger or UsageLedger({})).run(
        run_id, store.read_record(run_id).request.until
    )


def research(store: RunStore, run_id: str) -> ResearchRecord:
    return store.read_artifact(run_id, "research.json", ResearchRecord)


async def test_three_rounds(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    fakes = world(gap_reply("lithium price"), gap_reply("cobalt supply"))
    assert await run(cfg, run_id, fakes) == "done"
    events = store.read_events(run_id)
    started = [event.stage for event in events if isinstance(event, StageStarted)]
    loop = ["search", "fetch", "chunk", "prefilter", "score"]
    assert started == ["plan", *loop, "gap", *loop, "gap", *loop, "select", "write"]
    assert [event.data.round for event in events if isinstance(event, RoundDone)] == [1, 2, 3]
    assert [event.data.stop for event in events if isinstance(event, GapReady)] == [False, False]
    done = [event for event in events if isinstance(event, ResearchDone)]
    assert [(d.data.planned, d.data.ran, d.data.reason) for d in done] == [(3, 3, "max rounds")]
    plan = store.read_artifact(run_id, "plan.json", Plan)
    assert [(query.id, query.round) for query in plan.queries] == [("q0", 1), ("q1", 1), ("q2", 2), ("q3", 3)]
    record = research(store, run_id)
    assert [(r.round, r.query_ids, r.new_pages) for r in record.rounds] == [
        (1, ["q1"], 3),
        (2, ["q2"], 1),
        (3, ["q3"], 1),
    ]
    assert [r.note for r in record.rounds] == ["More on prices.", "More on prices.", ""]
    pages = store.read_items(run_id, "pages.jsonl", Page)
    assert sorted((page.source.uri, page.round) for page in pages)[-2:] == [
        ("https://d.test", 2),
        ("https://e.test", 3),
    ]
    assert store.summary(store.read_record(run_id)).rounds_ran == 3


async def test_coverage_sufficient(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    note = "Every sub-query has primary sources."
    assert await run(cfg, run_id, world(gap_reply(stop=True, note=note))) == "done"
    record = research(store, run_id)
    assert (record.ran, record.reason, record.note) == (1, "model judged coverage sufficient", note)
    names = kinds(store.read_events(run_id))
    assert names.index("research.done:gap") < names.index("stage.started:select")


async def test_no_new_sources(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    fakes = world(gap_reply("again"), gap_reply("lithium price"))
    assert await run(cfg, run_id, fakes) == "done"
    record = research(store, run_id)
    assert (record.planned, record.ran, record.reason) == (3, 2, "no new sources")
    assert (record.rounds[1].new_pages, record.rounds[1].known_pages) == (0, 1)
    assert record.note == "Follow-up searches returned only pages fetched in earlier rounds."
    assert len(planner_of(fakes).calls) == 2
    summary = store.summary(store.read_record(run_id))
    assert (summary.rounds_planned, summary.rounds_ran, summary.stop_reason) == (3, 2, "no new sources")


async def test_page_limit(tmp_path: Path) -> None:
    cfg = configured(tmp_path, rounds=2, fetch=FetchConfig(provider="firecrawl", max_pages=4))
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    assert await run(cfg, run_id, world(gap_reply("lithium price", "cobalt supply"))) == "done"
    record = research(store, run_id)
    assert (record.ran, record.reason) == (2, "page limit reached")
    assert [r.new_pages for r in record.rounds] == [2, 2]
    assert len(store.read_items(run_id, "pages.jsonl", Page)) == 4


@pytest.mark.parametrize(
    ("left", "later", "per_round", "results", "cap"),
    [
        (5, 0, 3, 10, 5),  # cap across rounds: the last round takes what is left
        (60, 2, 3, 10, 20),  # deep: the reserve leaves nothing, the even share is 20
        (40, 1, 3, 10, 20),  # deep, round 2
        (60, 1, 3, 5, 45),  # the reserve is smaller than the room
        (15, 0, 3, 10, 15),  # a single round
        (0, 2, 3, 10, 0),
    ],
)
def test_round_cap(left: int, later: int, per_round: int, results: int, cap: int) -> None:
    assert round_cap(left, later, per_round, results) == cap


async def test_round_cap_leaves_room_for_the_gap_step(tmp_path: Path) -> None:
    research_cfg = ResearchConfig(rounds=3, queries_per_round=1)
    cfg = settings(tmp_path).model_copy(
        update={"research": research_cfg, "fetch": FetchConfig(provider="firecrawl", max_pages=3)}
    )
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    fakes = world(gap_reply("lithium price"), gap_reply("cobalt supply"))
    assert await run(cfg, run_id, fakes) == "done"
    record = research(store, run_id)
    assert [r.new_pages for r in record.rounds] == [1, 1, 1]
    assert len([e for e in store.read_events(run_id) if isinstance(e, GapReady)]) == 2


def test_gap_budget_number(tmp_path: Path) -> None:
    assert gap_budget(configured(tmp_path), "q", []) == 4000


def test_auto_gap_budget(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    cfg = cfg.model_copy(
        update={
            "research": ResearchConfig(rounds=3, gap_context_tokens="auto"),
            "llm": cfg.llm.model_copy(
                update={"context_window": 1_000_000, "chars_per_token": 1.0, "token_margin": 1.0}
            ),
        }
    )
    queries = [Query(id="q0", text="b" * 299), Query(id="q1", text="c" * 200)]
    # 1000 query characters plus 299 + 1 + 200 for the queries joined by a newline: 1500 tokens.
    assert gap_budget(cfg, "a" * 1000, queries) == 1_000_000 - 2000 - 768 - 1500


def test_gap_budget_below_zero_fails(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    cfg = cfg.model_copy(
        update={
            "research": ResearchConfig(rounds=3, gap_context_tokens="auto"),
            "llm": cfg.llm.model_copy(update={"context_window": 2500}),
        }
    )
    with pytest.raises(ValueError, match=r"llm\.context_window"):
        gap_budget(cfg, "q", [])


async def test_known_page_not_paired(tmp_path: Path) -> None:
    searcher = FakeSearcher({**WORLD, "lithium price": ["https://a.test/x", "https://d.test"]})
    cfg = configured(tmp_path, rounds=2)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    fakes = world(gap_reply("lithium price"), searcher=searcher)
    assert await run(cfg, run_id, fakes) == "done"
    record = research(store, run_id)
    assert (record.rounds[1].new_pages, record.rounds[1].known_pages) == (1, 1)
    sources = {chunk.chunk_id: chunk.source_id for chunk in store.read_items(run_id, "chunks.jsonl", Chunk)}
    paired = {
        sources[c.chunk_id] for c in store.read_items(run_id, "candidates.jsonl", Candidate) if c.query_id == "q2"
    }
    page_ids = {page.source.uri: page.source.source_id for page in store.read_items(run_id, "pages.jsonl", Page)}
    assert paired == {page_ids["https://d.test"]}


async def test_gap_failure_keeps_run(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    assert await run(cfg, run_id, world("no json here")) == "done"
    assert research(store, run_id).reason == "gap step failed"
    gap_done = store.done_events(run_id)["gap"]
    assert any(warning.startswith("gap failed:") for warning in gap_done.data.warnings)
    assert (store.run_dir(run_id) / "report.md").read_text()


async def test_until_loop_stage(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web", until="score")
    fakes = world(gap_reply("lithium price"))
    assert await run(cfg, run_id, fakes) == "done"
    names = kinds(store.read_events(run_id))
    assert names[-2:] == ["stage.done:score", "run.done"]
    assert len(planner_of(fakes).calls) == 1


async def test_summed_usage(tmp_path: Path) -> None:
    ledger = UsageLedger({})

    class Counting(FakeLLM):
        async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion:
            ledger.record("llm", "plan", input_tokens=100)
            return await super().complete(messages, max_tokens=max_tokens)

    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    planner = Counting([PLAN_REPLY, gap_reply("lithium price"), gap_reply("cobalt supply")])
    fakes = adapters(searcher=FakeSearcher(WORLD), fetcher=FakeFetcher(PAGES_ALL), planner=planner)
    assert await run(cfg, run_id, fakes, ledger) == "done"
    costs = json.loads((store.run_dir(run_id) / "costs.json").read_text())
    assert costs["stages"]["gap"]["input_tokens"] == 200
    gap_events = [e for e in store.read_events(run_id) if isinstance(e, StageDone) and e.stage == "gap"]
    assert [e.data.usage.input_tokens for e in gap_events] == [100, 100]


async def test_sticky_fallback(tmp_path: Path) -> None:
    class Down(FakeScorer):
        async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
            self.calls.append((query, list(chunks)))
            raise RuntimeError("rerank down")

    down = Down("rerank")
    cfg = configured(tmp_path, rounds=2, score=ScoreConfig(provider="rerank"), select=SelectConfig(passthrough_chars=0))
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    fakes = world(gap_reply("lithium price"), scorers={"rerank": down})
    assert await run(cfg, run_id, fakes) == "done"
    score_done = [e for e in store.read_events(run_id) if isinstance(e, StageDone) and e.stage == "score"]
    assert [e.data.provider for e in score_done] == ["bm25", "bm25"]
    assert {score.scorer for score in store.read_items(run_id, "scores.jsonl", Score) if score.round == 2} == {"bm25"}
    assert down.calls
    assert all(query.round == 1 for query, _ in down.calls)


async def test_interrupted_in_round_two(tmp_path: Path) -> None:
    class Stops(FakeFetcher):
        async def fetch(self, url: str) -> Page:
            if url == "https://d.test":
                raise asyncio.CancelledError
            return await super().fetch(url)

    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg, sources="web")
    first = world(gap_reply("lithium price"), fetcher=Stops(PAGES_ALL))
    with pytest.raises(asyncio.CancelledError):
        await run(cfg, run_id, first)
    assert "search" not in store.finished_stages(run_id)
    planner = FakeLLM([gap_reply("lithium price"), gap_reply(stop=True)])
    fakes = adapters(searcher=FakeSearcher(WORLD), fetcher=FakeFetcher(PAGES_ALL), planner=planner)
    assert await run(cfg, run_id, fakes) == "done"
    assert "Queries already run" in planner.calls[0][1].content
    record = research(store, run_id)
    assert (record.ran, [r.query_ids for r in record.rounds]) == (2, [["q1"], ["q2"]])
    assert [query.id for query in store.read_artifact(run_id, "plan.json", Plan).queries] == ["q0", "q1", "q2"]


async def test_fork_from_score_reruns_loop(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    parent = new_run(store, cfg, sources="web")
    assert await run(cfg, parent, world(gap_reply("lithium price"), gap_reply("cobalt supply"))) == "done"
    child = store.fork(parent, "score", [], cfg).run_id
    assert set(store.finished_stages(child)) == {"load", "plan"}
    assert [query.id for query in store.read_artifact(child, "plan.json", Plan).queries] == ["q0", "q1"]
    planner = FakeLLM([gap_reply(stop=True)])
    fakes = adapters(searcher=FakeSearcher(WORLD), fetcher=FakeFetcher(PAGES_ALL), planner=planner)
    assert await run(cfg, child, fakes) == "done"
    assert research(store, child).ran == 1


async def test_rewrite_reuses_rounds(tmp_path: Path) -> None:
    cfg = configured(tmp_path)
    store = RunStore.from_settings(cfg)
    parent = new_run(store, cfg, sources="web")
    assert await run(cfg, parent, world(gap_reply("lithium price"), gap_reply("cobalt supply"))) == "done"
    child = store.fork(parent, "write", [], cfg).run_id
    assert (store.run_dir(child) / "research.json").read_text() == (store.run_dir(parent) / "research.json").read_text()
    assert len(store.read_artifact(child, "plan.json", Plan).queries) == 4
    assert "search" in store.finished_stages(child)
    assert await run(cfg, child, adapters()) == "done"
    assert store.summary(store.read_record(child)).rounds_ran == 3


async def test_single_round_unchanged(tmp_path: Path) -> None:
    cfg = configured(tmp_path, rounds=1)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg)
    assert await run(cfg, run_id, adapters()) == "done"
    names = kinds(store.read_events(run_id))
    assert not any(name.startswith(("round.done", "gap.ready", "research.done")) for name in names)
    assert store.done_events(run_id)["gap"].data.skipped
    assert not (store.run_dir(run_id) / "research.json").exists()
    assert QUERY

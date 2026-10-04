"""The runner end to end with fakes: steps, stage order, failures, devices, timeouts, cancellation, costs."""

import asyncio
import json
from pathlib import Path

import pytest

from tests.runner.helpers import PAGES, QUERY, Releases, adapters, kinds, new_run, settings
from wosarcher.adapters.fakes import FakeEmbedder, FakeFetcher, FakeLLM, FakeManaged, FakeScorer, FakeSearcher, healthy
from wosarcher.config import LLMConfig, PrefilterConfig, ScoreConfig, Settings
from wosarcher.http import UsageLedger
from wosarcher.models import (
    Chunk,
    Completion,
    Hit,
    Message,
    Page,
    PageFailed,
    PassagesScored,
    ProviderHealth,
    Query,
    RunCancelled,
    RunCancelledData,
    RunFailed,
    RunFailedData,
    Score,
    StageDone,
    StageFailed,
)
from wosarcher.ports import Adapters, Managed
from wosarcher.runner import Runner
from wosarcher.store import RunStore


def store_of(cfg: Settings) -> RunStore:
    return RunStore.from_settings(cfg)


async def run(cfg: Settings, run_id: str, fakes: Adapters | None = None, ledger: UsageLedger | None = None) -> str:
    return await Runner(store_of(cfg), cfg, fakes or adapters(), ledger or UsageLedger({})).run(
        run_id, store_of(cfg).read_record(run_id).request.until
    )


def ending(store: RunStore, run_id: str) -> RunFailedData | RunCancelledData:
    last = store.read_events(run_id)[-1]
    assert isinstance(last, RunFailed | RunCancelled)
    return last.data


def done_of(store: RunStore, run_id: str, stage: str) -> StageDone:
    return store.done_events(run_id)[stage]  # pyright: ignore[reportArgumentType]


async def test_full_run(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    (tmp_path / "notes.md").write_text("# Notes\nHydrometallurgy wins for battery recycling.\n")
    planner = FakeLLM(['{"queries": ["recycling cost"]}'])
    run_id = new_run(store, cfg, attachments=[str(tmp_path / "notes.md")])
    assert await run(cfg, run_id, adapters(planner=planner)) == "done"
    directory = store.run_dir(run_id)
    expected = {"request.json", "attachments", "files.jsonl", "plan.json", "initial.jsonl", "hits.jsonl"}
    expected |= {"pages.jsonl", "chunks.jsonl", "candidates.jsonl", "scores.jsonl", "context.json", "select.jsonl"}
    expected |= {"report.md", "report.json", "events.jsonl", "costs.json"}
    assert {path.name for path in directory.iterdir()} == expected
    events = store.read_events(run_id)
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    started = [event.stage for event in events if event.type == "stage.started"]
    assert started == ["load", "plan", "search", "fetch", "chunk", "prefilter", "score", "select", "write"]
    assert events[-1].type == "run.done"
    assert "Hydrometallurgy" in planner.calls[0][1].content
    assert "https://a.test/x" in planner.calls[0][1].content
    assert store.read_items(run_id, "files.jsonl", Page)[0].source.uri == "notes.md"
    assert "## References" in (directory / "report.md").read_text()


async def test_initial_hits_reach_search_and_hit_events(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    searcher = FakeSearcher({QUERY: ["https://a.test/x"], "recycling cost": ["https://a.test/x", "https://c.test"]})
    run_id = new_run(store, cfg, until="search")
    assert await run(cfg, run_id, adapters(searcher=searcher)) == "done"
    assert [query.text for query in searcher.calls] == [QUERY, "recycling cost"]
    hits = {hit.url: hit.query_ids for hit in store.read_items(run_id, "hits.jsonl", Hit)}
    assert hits == {"https://a.test/x": ["q0", "q1"], "https://c.test": ["q1"]}
    assert "hit.found:plan" in kinds(store.read_events(run_id))


async def test_failing_page_continues(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    run_id = new_run(store, cfg, until="fetch")
    fetcher = FakeFetcher(PAGES, failing={"https://b.test"})
    assert await run(cfg, run_id, adapters(fetcher=fetcher)) == "done"
    failed = [event for event in store.read_events(run_id) if isinstance(event, PageFailed)]
    assert [event.data.url for event in failed] == ["https://b.test"]
    assert done_of(store, run_id, "fetch").data.count == 2


async def test_planner_error_fails_run(tmp_path: Path) -> None:
    class Broken(FakeLLM):
        async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion:
            raise RuntimeError("llm down")

    cfg = settings(tmp_path)
    store = store_of(cfg)
    searcher = FakeSearcher({QUERY: ["https://a.test/x"]})
    run_id = new_run(store, cfg)
    assert await run(cfg, run_id, adapters(planner=Broken(), searcher=searcher)) == "failed"
    last = ending(store, run_id)
    assert isinstance(last, RunFailedData)
    assert (last.stage, last.error) == ("plan", "llm down")
    assert len(searcher.calls) == 1


async def test_until_select(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    writer = FakeLLM()
    run_id = new_run(store, cfg, until="select")
    assert await run(cfg, run_id, adapters(writer=writer)) == "done"
    assert (store.run_dir(run_id) / "context.json").is_file()
    assert not (store.run_dir(run_id) / "report.md").exists()
    assert writer.calls == []
    assert store.read_events(run_id)[-1].type == "run.done"


async def test_files_only(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    (tmp_path / "notes.md").write_text("# Notes\nBattery recycling notes.\n")
    searcher, fetcher = FakeSearcher(), FakeFetcher()
    run_id = new_run(store, cfg, sources="files", attachments=[str(tmp_path / "notes.md")])
    assert await run(cfg, run_id, adapters(searcher=searcher, fetcher=fetcher)) == "done"
    assert (searcher.calls, fetcher.calls) == ([], [])
    assert done_of(store, run_id, "search").data.skipped
    assert done_of(store, run_id, "fetch").data.skipped


async def test_web_without_pages_fails(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    run_id = new_run(store, cfg, sources="web")
    assert await run(cfg, run_id, adapters(fetcher=FakeFetcher())) == "failed"
    assert ending(store, run_id).stage == "fetch"
    assert done_of(store, run_id, "load").data.skipped


async def test_both_without_web_pages_continues(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    (tmp_path / "notes.md").write_text("# Notes\nBattery recycling notes.\n")
    run_id = new_run(store, cfg, attachments=[str(tmp_path / "notes.md")])
    assert await run(cfg, run_id, adapters(fetcher=FakeFetcher())) == "done"
    assert done_of(store, run_id, "fetch").data.count == 0


class BrokenScorer(FakeScorer):
    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
        raise RuntimeError("rerank down")


async def test_scorer_fallback_reported(tmp_path: Path) -> None:
    cfg = settings(tmp_path).model_copy(update={"score": ScoreConfig(provider="rerank")})
    cfg = cfg.model_copy(update={"select": cfg.select.model_copy(update={"passthrough_chars": 0})})
    store = store_of(cfg)
    run_id = new_run(store, cfg, until="score")
    assert await run(cfg, run_id, adapters(scorers={"rerank": BrokenScorer("rerank")})) == "done"
    events = store.read_events(run_id)
    failed = [event for event in events if isinstance(event, StageFailed)]
    assert [(e.data.error, e.data.next) for e in failed] == [("rerank: rerank down", "bm25")]
    assert done_of(store, run_id, "score").data.provider == "bm25"
    scored = [event for event in events if isinstance(event, PassagesScored)]
    assert [event.data.query_id for event in scored] == ["q0", "q1"]
    assert all(passage.uri for event in scored for passage in event.data.passages)


class BrokenEmbedder(FakeEmbedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("connection refused")


def embeddings_settings(tmp_path: Path, passthrough_chars: int) -> Settings:
    cfg = settings(tmp_path)
    return cfg.model_copy(
        update={
            "prefilter": PrefilterConfig(provider="embeddings", model="bge-small-en-v1.5"),
            "select": cfg.select.model_copy(update={"passthrough_chars": passthrough_chars}),
        }
    )


async def test_prefilter_provider_keeps_model(tmp_path: Path) -> None:
    cfg = embeddings_settings(tmp_path, 0)
    store = store_of(cfg)
    run_id = new_run(store, cfg, until="prefilter")
    assert await run(cfg, run_id) == "done"
    done = done_of(store, run_id, "prefilter").data
    assert (done.provider, done.passthrough) == ("embeddings:bge-small-en-v1.5", [])


async def test_prefilter_fallback_reported(tmp_path: Path) -> None:
    cfg = embeddings_settings(tmp_path, 0)
    store = store_of(cfg)
    run_id = new_run(store, cfg, until="prefilter")
    assert await run(cfg, run_id, adapters(embedder=BrokenEmbedder())) == "done"
    done = done_of(store, run_id, "prefilter").data
    assert done.provider == "bm25"
    assert "embeddings prefilter failed, used bm25: connection refused" in done.warnings


async def test_prefilter_passthrough_reported(tmp_path: Path) -> None:
    cfg = embeddings_settings(tmp_path, 60)
    store = store_of(cfg)
    run_id = new_run(store, cfg, until="prefilter")
    assert await run(cfg, run_id) == "done"
    assert done_of(store, run_id, "prefilter").data.passthrough == ["q1"]


async def test_report_streams_into_file(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    run_id = new_run(store, cfg)
    seen: list[str] = []

    def listener(event: object) -> None:
        if getattr(event, "type", "") == "report.delta" and not seen:
            seen.append((store.run_dir(run_id) / "report.md").read_text())

    runner = Runner(store, cfg, adapters(), UsageLedger({}), [listener])
    assert await runner.run(run_id) == "done"
    assert seen == ["Battery "]
    assert "report.delta" not in {event.type for event in store.read_events(run_id)}


async def test_report_continued(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    store = store_of(cfg)
    run_id = new_run(store, cfg)
    writer = FakeLLM(["First part [1].", " Second part [1]."])
    writer.finish_reasons = ["length", "stop"]
    runner = Runner(store, cfg, adapters(writer=writer), UsageLedger({}), [])
    assert await runner.run(run_id) == "done"
    markdown = (store.run_dir(run_id) / "report.md").read_text()
    assert "First part" in markdown
    assert "Second part" in markdown
    report = json.loads((store.run_dir(run_id) / "report.json").read_text())
    assert (report["continuations"], report["truncated"]) == (1, False)


async def test_score_timeout(tmp_path: Path) -> None:
    class Slow(FakeScorer):
        async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
            await asyncio.sleep(1)
            return []

    cfg = settings(tmp_path, stage_timeouts={"score": 0.05}).model_copy(
        update={"score": ScoreConfig(provider="rerank")}
    )
    cfg = cfg.model_copy(update={"select": cfg.select.model_copy(update={"passthrough_chars": 0})})
    store = store_of(cfg)
    run_id = new_run(store, cfg)
    assert await run(cfg, run_id, adapters(scorers={"rerank": Slow("rerank")})) == "failed"
    last = ending(store, run_id)
    assert isinstance(last, RunFailedData)
    assert last.stage == "score"
    assert "timed out" in last.error


def gpu(tmp_path: Path, score_device: str, llm_device: str) -> Settings:
    cfg = settings(tmp_path, gpu_policy="exclusive")
    return cfg.model_copy(
        update={
            "score": ScoreConfig(provider="rerank", device=score_device, release="llama-swap"),
            "llm": LLMConfig(provider="llm", device=llm_device, release="llama-swap"),
            "select": cfg.select.model_copy(update={"passthrough_chars": 0}),
        }
    )


async def test_exclusive_release_between_score_and_write(tmp_path: Path) -> None:
    cfg = gpu(tmp_path, "d0", "d0")
    store = store_of(cfg)
    released: list[str] = []
    managed: dict[str, Managed] = {"score": Releases("score", released), "llm": Releases("llm", released)}
    run_id = new_run(store, cfg)
    fakes = adapters(scorers={"rerank": FakeScorer("rerank")}, managed=managed)
    assert await run(cfg, run_id, fakes) == "done"
    names = kinds(store.read_events(run_id))
    after = names[names.index("stage.done:score") :][:4]
    assert after == ["stage.done:score", "resource.waiting:write", "resource.released:write", "stage.started:select"]
    assert released == ["llm", "score"]
    assert not [name for name in names[names.index("stage.started:select") :] if name.startswith("resource.")]


async def test_different_devices_no_release(tmp_path: Path) -> None:
    cfg = gpu(tmp_path, "d0", "d1")
    store = store_of(cfg)
    released: list[str] = []
    managed: dict[str, Managed] = {"score": Releases("score", released), "llm": Releases("llm", released)}
    run_id = new_run(store, cfg)
    assert await run(cfg, run_id, adapters(scorers={"rerank": FakeScorer("rerank")}, managed=managed)) == "done"
    assert released == []
    assert not [name for name in kinds(store.read_events(run_id)) if name.startswith("resource.")]


async def test_cancel_releases_current_stage(tmp_path: Path) -> None:
    started = asyncio.Event()

    class Slow(FakeScorer):
        async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
            started.set()
            await asyncio.sleep(10)
            return []

    cfg = gpu(tmp_path, "d0", "d1")
    store = store_of(cfg)
    released: list[str] = []
    run_id = new_run(store, cfg)
    fakes = adapters(scorers={"rerank": Slow("rerank")}, managed={"score": Releases("score", released)})
    task = asyncio.create_task(Runner(store, cfg, fakes, UsageLedger({})).run(run_id))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    last = ending(store, run_id)
    assert isinstance(last, RunCancelledData)
    assert last.stage == "score"
    assert released == ["score"]


async def test_costs(tmp_path: Path) -> None:
    ledger = UsageLedger({})

    class Counting(FakeLLM):
        async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion:
            ledger.record("llm", "plan", input_tokens=100)
            return await super().complete(messages, max_tokens=max_tokens)

    cfg = settings(tmp_path)
    store = store_of(cfg)
    run_id = new_run(store, cfg)
    assert await run(cfg, run_id, adapters(planner=Counting(['{"queries": ["recycling cost"]}'])), ledger) == "done"
    costs = json.loads((store.run_dir(run_id) / "costs.json").read_text())
    assert costs["stages"]["plan"]["input_tokens"] == 100
    assert costs["total"]["input_tokens"] == 100
    assert costs["providers"]["llm"]["input_tokens"] == 100
    assert done_of(store, run_id, "plan").data.usage.input_tokens == 100


async def test_page_failed_reason_short(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    error = "\n".join(f"line {n} " + "x" * 90 for n in range(30))

    class Loud(FakeFetcher):
        async def fetch(self, url: str) -> Page:
            if url == "https://b.test":
                raise RuntimeError(error)
            return await super().fetch(url)

    cfg = settings(tmp_path)
    store = store_of(cfg)
    run_id = new_run(store, cfg, until="fetch")
    assert await run(cfg, run_id, adapters(fetcher=Loud(PAGES))) == "done"
    (failed,) = [event for event in store.read_events(run_id) if isinstance(event, PageFailed)]
    assert len(failed.data.reason) <= 200
    assert "\n" not in failed.data.reason
    assert "fetch https://b.test failed:" in caplog.text
    assert "line 29 " in caplog.text


async def test_cancel_writes_costs(tmp_path: Path) -> None:
    ledger = UsageLedger({})
    started = asyncio.Event()

    class Counting(FakeLLM):
        async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion:
            ledger.record("llm", "plan", input_tokens=100)
            return await super().complete(messages, max_tokens=max_tokens)

    class Stuck(FakeFetcher):
        async def fetch(self, url: str) -> Page:
            started.set()
            await asyncio.sleep(10)
            raise AssertionError("not cancelled")

    cfg = settings(tmp_path)
    store = store_of(cfg)
    run_id = new_run(store, cfg)
    fakes = adapters(planner=Counting(['{"queries": ["recycling cost"]}']), fetcher=Stuck(PAGES))
    task = asyncio.create_task(Runner(store, cfg, fakes, ledger).run(run_id))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ending(store, run_id) == RunCancelledData(stage="fetch")
    costs = json.loads((store.run_dir(run_id) / "costs.json").read_text())
    assert (costs["stages"]["plan"]["input_tokens"], costs["total"]["input_tokens"]) == (100, 100)


class Probed(FakeManaged):
    """A Managed that records each probe in a shared list; `down` makes the probe fail."""

    def __init__(self, name: str, log: list[str], down: bool = False) -> None:
        health = healthy(name, "fake")
        if down:
            health = health.model_copy(update={"status": "failed", "error": "connection refused"})
        super().__init__(health)
        self.name, self.log = name, log

    async def probe(self) -> ProviderHealth:
        self.log.append(self.name)
        return self.health


def preflight_settings(tmp_path: Path, mode: str) -> Settings:
    cfg = settings(tmp_path, preflight=mode)
    return cfg.model_copy(
        update={
            "score": ScoreConfig(provider="rerank"),
            "llm": LLMConfig(provider="llm", device="desktop:gpu0"),
        }
    )


def probed(log: list[str], down: str | None = None) -> dict[str, Managed]:
    return {name: Probed(name, log, name == down) for name in ("search", "fetch", "score", "llm")}


async def test_preflight_default_sends_no_probe(tmp_path: Path) -> None:
    cfg = preflight_settings(tmp_path, "off")
    log: list[str] = []
    run_id = new_run(store_of(cfg), cfg)
    await run(cfg, run_id, adapters(scorers={"rerank": FakeScorer("rerank")}, managed=probed(log)))
    assert log == []


async def test_preflight_cloud_skips_local(tmp_path: Path) -> None:
    cfg = preflight_settings(tmp_path, "cloud")
    log: list[str] = []
    run_id = new_run(store_of(cfg), cfg)
    assert await run(cfg, run_id, adapters(scorers={"rerank": FakeScorer("rerank")}, managed=probed(log))) == "done"
    assert "search" in log
    assert "llm" not in log


async def test_preflight_down_fails_early(tmp_path: Path) -> None:
    cfg = preflight_settings(tmp_path, "all")
    store = store_of(cfg)
    log: list[str] = []
    run_id = new_run(store, cfg)
    fakes = adapters(scorers={"rerank": FakeScorer("rerank")}, managed=probed(log, down="score"))
    assert await run(cfg, run_id, fakes) == "failed"
    failed = ending(store, run_id)
    assert isinstance(failed, RunFailedData)
    assert failed.stage == "score"
    assert failed.error.startswith("preflight: score")
    assert not [name for name in kinds(store.read_events(run_id)) if name.startswith("stage.started")]


async def test_preflight_skipped_stages_not_probed(tmp_path: Path) -> None:
    cfg = preflight_settings(tmp_path, "all")
    store = store_of(cfg)
    (tmp_path / "notes.md").write_text("# Notes\nBattery recycling notes.\n")
    log: list[str] = []
    run_id = new_run(store, cfg, sources="files", attachments=[str(tmp_path / "notes.md")])
    await run(cfg, run_id, adapters(scorers={"rerank": FakeScorer("rerank")}, managed=probed(log)))
    assert "search" not in log
    assert "fetch" not in log
    assert "score" in log

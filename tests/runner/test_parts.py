"""Runner parts: caching wrappers, the event log, and the device rule."""

from pathlib import Path

import pytest

from wosarcher.adapters.fakes import FakeFetcher
from wosarcher.config import LLMConfig, PrefilterConfig, RunConfig, ScoreConfig, Settings
from wosarcher.models import ReportTextData, RunQueuedData, RunRequest, Stage, StageProgress
from wosarcher.runner.caches import CachedFetcher, EmbeddingMapping
from wosarcher.runner.devices import needs_release
from wosarcher.runner.events import EventLog, snapshot_event
from wosarcher.runner.steps import short_reason
from wosarcher.store import RunStore
from wosarcher.store.caches import EmbeddingCache, PageCache


async def test_cached_fetcher(tmp_path: Path) -> None:
    fake = FakeFetcher({"https://a.test": "text"})
    first = CachedFetcher(fake, PageCache(tmp_path, 24))
    await first.fetch("https://a.test")
    second = CachedFetcher(fake, PageCache(tmp_path, 24))
    page = await second.fetch("https://a.test")
    assert page.text == "text"
    assert fake.calls == ["https://a.test"]
    assert second.cached == {"https://a.test"}


def test_embedding_mapping(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path)
    EmbeddingMapping(cache, "m", 2)["k1"] = [1.0, 2.0]
    assert EmbeddingMapping(cache, "m", 2)["k1"] == [1.0, 2.0]
    assert "k1" in EmbeddingMapping(cache, "m", 2)
    assert "k1" not in EmbeddingMapping(cache, "other", 2)
    assert list(EmbeddingMapping(cache, "m", 2)) == ["k1"]


@pytest.fixture
def run(tmp_path: Path) -> tuple[RunStore, str]:
    store = RunStore(tmp_path / "runs", tmp_path / "cache")
    return store, store.create(RunRequest(query="q"), "p", [], Settings(), []).run_id


def test_log_before_publish(run: tuple[RunStore, str]) -> None:
    store, run_id = run
    seen: list[int] = []

    def listener(event: object) -> None:
        logged = [e.seq for e in store.read_events(run_id)]
        seen.append(len(logged))

    log = EventLog(store, run_id, [listener])
    for _ in range(3):
        log.emit("run.queued", None, RunQueuedData(position=0, limit=1))
    assert [e.seq for e in store.read_events(run_id)] == [1, 2, 3]
    assert seen == [1, 2, 3]


def test_deltas_not_logged(run: tuple[RunStore, str]) -> None:
    store, run_id = run
    received: list[object] = []
    log = EventLog(store, run_id, [received.append])
    log.emit("run.queued", None, RunQueuedData(position=0, limit=1))
    deltas = [log.live("report.delta", "write", ReportTextData(text=str(n))) for n in range(40)]
    assert len(received) == 41
    assert all(delta.seq == 1 for delta in deltas)
    assert [e.type for e in store.read_events(run_id)] == ["run.queued"]


def test_progress_throttled(run: tuple[RunStore, str]) -> None:
    store, run_id = run
    now = [0.0]
    log = EventLog(store, run_id, clock=lambda: now[0])
    for n in range(1000):
        now[0] = n * 0.0001
        log.progress("fetch", n + 1, 1000)
    log.flush("fetch")
    events = store.read_events(run_id)
    assert [e.data.done for e in events if isinstance(e, StageProgress)] == [1, 1000]


def test_snapshot(run: tuple[RunStore, str]) -> None:
    store, run_id = run
    EventLog(store, run_id).emit("run.queued", None, RunQueuedData(position=0, limit=1))
    store.append_report(run_id, "Intro")
    snapshot = snapshot_event(store, run_id)
    assert (snapshot.data.text, snapshot.seq, snapshot.type) == ("Intro", 1, "report.snapshot")


def devices(policy: str = "exclusive", score: str | None = "d0", llm: str | None = "d0") -> Settings:
    return Settings(
        run=RunConfig.model_validate({"gpu_policy": policy}),
        prefilter=PrefilterConfig(),
        score=ScoreConfig(provider="rerank", device=score),
        llm=LLMConfig(provider="openai", device=llm),
    )


@pytest.mark.parametrize(
    ("cfg", "done", "remaining", "expected"),
    [
        (devices(), "score", ["select", "write"], True),
        (devices(llm="d1"), "score", ["select", "write"], False),
        (devices(score=None), "plan", ["search", "fetch", "chunk", "prefilter", "score", "select", "write"], False),
        (devices(), "score", ["select"], False),
        (devices("shared"), "score", ["select", "write"], False),
    ],
    ids=["same-device", "different-device", "same-block", "no-later-gpu-stage", "shared"],
)
def test_needs_release(cfg: Settings, done: Stage, remaining: list[Stage], expected: bool) -> None:
    assert needs_release(done, remaining, cfg) is expected


def test_short_reason() -> None:
    assert short_reason("HTTP 500") == "HTTP 500"
    assert short_reason("HTTP 500\ntraceback") == "HTTP 500…"
    cut = short_reason("x" * 300)
    assert (len(cut), cut[-1]) == (200, "…")

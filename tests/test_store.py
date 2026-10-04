"""Run store: layout, record, attachments, artifacts, event log, fork, listing, costs, caches."""

import json
from pathlib import Path

import pytest

from wosarcher.config import RunConfig, Settings, resolve
from wosarcher.models import (
    STAGES,
    Hit,
    Page,
    RunCancelledData,
    RunCosts,
    RunDoneData,
    RunFailedData,
    RunQueuedData,
    RunRequest,
    RunStartedData,
    Source,
    StageDoneData,
    UsageTotals,
)
from wosarcher.store import RunStore, RunStoreError, new_run_id
from wosarcher.store.caches import EmbeddingCache, PageCache

REQUEST = RunRequest(query="battery recycling")


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs", tmp_path / "cache")


def create(store: RunStore, attachments: list[str] | None = None, settings: Settings | None = None) -> str:
    return store.create(REQUEST, "workstation", [], settings or Settings(), attachments or []).run_id


def finish(store: RunStore, run_id: str, *stages: str) -> None:
    for stage in stages:
        store.append_event(run_id, "stage.done", stage, StageDoneData(count=1, seconds=0.1))  # pyright: ignore[reportArgumentType]


def test_defaults_use_xdg(tmp_path: Path) -> None:
    env = {"XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CACHE_HOME": str(tmp_path / "cache")}
    store = RunStore.from_settings(Settings(), env)
    assert store.runs_dir == tmp_path / "data" / "wosarcher" / "runs"
    assert store.cache_dir == tmp_path / "cache" / "wosarcher"
    chosen = RunStore.from_settings(Settings(run=RunConfig(runs_dir=tmp_path / "r")), env)
    assert chosen.runs_dir == tmp_path / "r"


def test_run_ids_sort_by_time() -> None:
    first = new_run_id()
    second = new_run_id()
    assert first < second


def test_secrets_redacted(store: RunStore) -> None:
    env = {"XDG_CONFIG_HOME": "/nonexistent", "WOSARCHER_SCORE__API_KEY": "sk-secret"}
    run_id = create(store, settings=resolve("workstation", [], env))
    text = (store.run_dir(run_id) / "request.json").read_text()
    assert '"api_key": "***"' in text
    assert "sk-secret" not in text
    record = store.read_record(run_id)
    assert (record.version, record.parent_run_id, record.fork_from) == (1, None, None)


def test_attachments_copied(store: RunStore, tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    (notes / "a").mkdir(parents=True)
    (notes / "b").mkdir()
    (notes / "a" / "x.md").write_text("# A")
    (notes / "b" / "x.md").write_text("# B")
    (tmp_path / "one.md").write_text("one")
    (tmp_path / "two.txt").write_text("two")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "one.md").write_text("other one")
    run_id = create(
        store, [str(notes), str(tmp_path / "*.txt"), str(tmp_path / "one.md"), str(tmp_path / "other/one.md")]
    )
    record = store.read_record(run_id)
    assert record.request.attachments == ["notes/a/x.md", "notes/b/x.md", "two.txt", "one.md", "one-2.md"]
    (tmp_path / "one.md").unlink()
    copied = store.run_dir(run_id) / "attachments"
    assert (copied / "one.md").read_text() == "one"
    assert (copied / "one-2.md").read_text() == "other one"


def test_missing_attachment_creates_nothing(store: RunStore, tmp_path: Path) -> None:
    with pytest.raises(RunStoreError, match="no file matches"):
        create(store, [str(tmp_path / "nope.md")])
    assert not store.runs_dir.exists()


def test_artifacts_round_trip(store: RunStore) -> None:
    run_id = create(store)
    hits = [Hit(url="https://a.test", title="A", snippet="", rank=1, query_ids=["q0"])]
    store.write_artifact(run_id, "hits.jsonl", hits)
    costs = RunCosts(stages={}, providers={}, total=UsageTotals())
    store.write_artifact(run_id, "costs.json", costs)
    assert store.read_items(run_id, "hits.jsonl", Hit) == hits
    assert store.read_artifact(run_id, "costs.json", RunCosts) == costs
    assert not list(store.run_dir(run_id).glob("*.tmp"))


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\x85"])
def test_items_with_unicode_line_separators(store: RunStore, separator: str) -> None:
    # JSON keeps these characters raw; only "\n" may end a JSONL record.
    run_id = create(store)
    hits = [Hit(url="https://a.test", title=f"A{separator}B", snippet=f"x{separator}y", rank=1, query_ids=["q0"])]
    store.write_artifact(run_id, "hits.jsonl", hits)
    assert store.read_items(run_id, "hits.jsonl", Hit) == hits


def test_seq_continues_in_new_store(store: RunStore) -> None:
    run_id = create(store)
    for _ in range(41):
        store.append_event(run_id, "run.queued", None, RunQueuedData(position=0))
    other = RunStore(store.runs_dir, store.cache_dir)
    event = other.append_event(run_id, "run.failed", None, RunFailedData(stage=None, error="crashed"))
    assert event.seq == 42
    assert [e.seq for e in store.read_events(run_id)] == list(range(1, 43))
    assert [e.seq for e in store.read_events(run_id, since=40)] == [41, 42]


def test_stage_finished_only_with_done_event(store: RunStore) -> None:
    run_id = create(store)
    finish(store, run_id, "load", "plan")
    store.write_text(run_id, "scores.jsonl", '{"partial": ')
    assert store.finished_stages(run_id) == {"load", "plan"}


def finished_run(store: RunStore) -> str:
    run_id = create(store)
    finish(store, run_id, *STAGES)
    for stage, names in (("context.json", "{}"), ("select.jsonl", ""), ("pages.jsonl", ""), ("report.md", "old")):
        store.write_text(run_id, stage, names)
    return run_id


def test_fork_from_write(store: RunStore) -> None:
    parent = finished_run(store)
    record = store.fork(parent, "write", ["write.tone=critical"], Settings())
    child = store.run_dir(record.run_id)
    assert (child / "context.json").is_file()
    assert (child / "select.jsonl").is_file()
    assert not (child / "report.md").exists()
    assert (record.version, record.parent_run_id, record.fork_from) == (2, parent, "write")
    assert record.changes == ["write.tone=critical"]
    assert store.finished_stages(record.run_id) == set(STAGES[:-1])
    done = store.done_events(record.run_id)
    assert all(event.data.copied_from == parent for event in done.values())


def test_fork_of_unfinished_run(store: RunStore) -> None:
    parent = create(store)
    finish(store, parent, "load", "plan", "search", "fetch")
    with pytest.raises(RunStoreError, match="chunk"):
        store.fork(parent, "score", [], Settings())


def test_lineage(store: RunStore) -> None:
    a = finished_run(store)
    b = store.fork(a, "write", [], Settings())
    finish(store, b.run_id, "write")
    c = store.fork(b.run_id, "write", ["write.words=300"], Settings())
    assert (b.version, b.parent_run_id) == (2, a)
    assert (c.version, c.parent_run_id) == (3, b.run_id)
    assert c.overrides == ["write.words=300"]


def test_fork_of_fork_copied_from(store: RunStore) -> None:
    a = finished_run(store)
    b = store.fork(a, "score", [], Settings())
    finish(store, b.run_id, *STAGES[STAGES.index("score") :])
    c = store.fork(b.run_id, "write", [], Settings())
    done = store.done_events(c.run_id)
    before_score = STAGES[: STAGES.index("score")]
    assert all(done[stage].data.copied_from == a for stage in before_score)
    assert [done[stage].data.copied_from for stage in ("score", "select")] == [b.run_id, b.run_id]


def test_second_fork_version(store: RunStore) -> None:
    a = finished_run(store)
    b = store.fork(a, "write", [], Settings())
    c = store.fork(b.run_id, "write", [], Settings())
    assert (store.read_record(a).version, b.version, c.version) == (1, 2, 3)


def test_two_forks_of_first_version(store: RunStore) -> None:
    a = finished_run(store)
    b = store.fork(a, "write", [], Settings())
    d = store.fork(a, "write", [], Settings())
    assert (b.version, d.version, d.parent_run_id) == (2, 3, a)


def test_list_statuses(store: RunStore) -> None:
    started = RunStartedData(query="q", profile="p", parent_run_id=None, version=1, until=None)
    ends = {
        "done": ("run.done", RunDoneData(until=None, totals=UsageTotals())),
        "failed": ("run.failed", RunFailedData(stage="fetch", error="x")),
        "cancelled": ("run.cancelled", RunCancelledData(stage="fetch")),
        "interrupted": None,
    }
    expected: dict[str, str] = {}
    for status, end in ends.items():
        run_id = create(store)
        store.append_event(run_id, "run.started", None, started)
        if end:
            store.append_event(run_id, end[0], None, end[1])
        expected[run_id] = status
    listed = store.list_runs()
    assert {run.run_id: run.status for run in listed} == expected
    assert [run.run_id for run in listed] == sorted(expected, reverse=True)
    assert len(store.list_runs(limit=2)) == 2


def test_list_ignores_dot_dirs(store: RunStore) -> None:
    first, second = create(store), create(store)
    (store.runs_dir / ".queue" / "x").mkdir(parents=True)
    assert {run.run_id for run in store.list_runs()} == {first, second}


def test_write_costs(store: RunStore) -> None:
    run_id = create(store)
    costs = RunCosts(
        stages={"plan": UsageTotals(input_tokens=100, cost=0.1)},
        providers={"llm": UsageTotals(input_tokens=100, cost=0.1)},
        total=UsageTotals(input_tokens=100, cost=0.1),
    )
    store.write_costs(run_id, costs)
    written = json.loads((store.run_dir(run_id) / "costs.json").read_text())
    assert set(written) == {"stages", "providers", "total"}
    assert written["stages"]["plan"]["cost"] == 0.1


def page(url: str = "https://a.test/x") -> Page:
    return Page(source=Source(source_id="s", kind="web", uri=url, title="A"), text="text")


def test_page_cache(tmp_path: Path) -> None:
    now = [1000.0]
    cache = PageCache(tmp_path, ttl_hours=1, clock=lambda: now[0])
    assert cache.get("https://a.test/x") is None
    cache.put(page())
    assert cache.get("https://A.test/x/#top") == page()
    now[0] += 3600
    assert cache.get("https://a.test/x") is None


def test_page_cache_disabled(tmp_path: Path) -> None:
    cache = PageCache(tmp_path, ttl_hours=0)
    cache.put(page())
    assert cache.get("https://a.test/x") is None
    assert not list(tmp_path.iterdir())


def test_embedding_cache(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path)
    cache.put("model-a", 2, "ab12", [0.5, 0.25])
    assert cache.get("model-a", 2, "ab12") == [0.5, 0.25]
    assert cache.get("model-b", 2, "ab12") is None
    assert cache.get("model-a", 3, "ab12") is None


def test_embedding_cache_rejects_wrong_dimension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"3 dimensions, expected 4 for model model-a"):
        EmbeddingCache(tmp_path).put("model-a", 4, "ab12", [0.5, 0.25, 0.125])
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def append_raw(store: RunStore, run_id: str, text: str) -> None:
    with (store.run_dir(run_id) / "events.jsonl").open("a", encoding="utf-8") as log:
        log.write(text)


def test_read_events_skips_bad_lines(store: RunStore) -> None:
    run_id = create(store)
    store.append_event(run_id, "run.queued", None, RunQueuedData(position=0))
    append_raw(store, run_id, "not json\n")
    append_raw(store, run_id, '{"seq": 2, "run_id": "r", "ts": "2026-01-01T00:00:00Z", "type": "stage.paused"}\n')
    store.append_event(run_id, "run.queued", None, RunQueuedData(position=0))
    assert [e.seq for e in store.read_events(run_id)] == [1, 2]


def nine_and_half(store: RunStore) -> str:
    run_id = create(store)
    for _ in range(9):
        store.append_event(run_id, "run.queued", None, RunQueuedData(position=0))
    append_raw(store, run_id, '{"seq": 10, "run_id": "r", "ts": "2026-01')
    return run_id


def test_tail_seq_ignores_partial_line(store: RunStore) -> None:
    assert store.tail_seq(nine_and_half(store)) == 9


def test_tail_seq_long_line(store: RunStore) -> None:
    run_id = create(store)
    store.append_event(run_id, "run.queued", None, RunQueuedData(position=0))
    store.append_event(run_id, "run.failed", None, RunFailedData(stage=None, error="x" * 21000))
    assert store.tail_seq(run_id) == 2


def test_seq_across_two_stores(store: RunStore) -> None:
    run_id = create(store)
    other = RunStore(store.runs_dir, store.cache_dir)
    seqs = [s.append_event(run_id, "run.queued", None, RunQueuedData(position=0)).seq for s in (store, other, store)]
    assert seqs == [1, 2, 3]


def test_append_after_partial_line(store: RunStore) -> None:
    run_id = nine_and_half(store)
    event = store.append_event(run_id, "run.cancelled", None, RunCancelledData(stage=None))
    assert event.seq == 10
    assert (store.run_dir(run_id) / "events.jsonl").read_text().splitlines()[-1] == event.model_dump_json()
    assert [e.seq for e in store.read_events(run_id)] == list(range(1, 11))


def test_summary_error_and_end_stage(store: RunStore) -> None:
    failed = create(store)
    store.append_event(failed, "run.failed", "fetch", RunFailedData(stage="fetch", error="no output"))
    summary = store.summary(store.read_record(failed))
    assert (summary.status, summary.error, summary.end_stage) == ("failed", "no output", "fetch")
    done = create(store)
    store.append_event(done, "run.done", None, RunDoneData(until=None, totals=UsageTotals()))
    summary = store.summary(store.read_record(done))
    assert (summary.error, summary.end_stage) == (None, None)


def test_depth_recorded(store: RunStore) -> None:
    overrides = ["write.words=800"]
    settings = resolve(None, overrides, {}, depth="deep")
    request = RunRequest(query="battery recycling", depth="deep")
    run_id = store.create(request, "workstation", overrides, settings, []).run_id
    saved = json.loads((store.run_dir(run_id) / "request.json").read_text())
    assert saved["request"]["depth"] == "deep"
    assert saved["overrides"] == ["write.words=800"]
    assert saved["settings"]["plan"]["max_sub_queries"] == 5
    assert store.list_runs()[0].depth == "deep"


def test_fork_keeps_depth(store: RunStore) -> None:
    run_id = store.create(RunRequest(query="q", depth="quick"), "workstation", [], Settings(), []).run_id
    finish(store, run_id, *STAGES[:-1])
    record = store.fork(run_id, "write", [], Settings())
    assert record.request.depth == "quick"

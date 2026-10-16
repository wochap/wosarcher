"""Run store: layout, record, attachments, artifacts, event log, fork, listing, costs, caches."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from tests.fixtures.config import MINIMAL_CONFIG, write_config
from wosarcher.config import (
    PlanConfig,
    RunConfig,
    ScoreConfig,
    Settings,
    list_depths,
    read_depth,
    read_profile,
    resolve,
    store_profile,
)
from wosarcher.models import (
    STAGES,
    Answer,
    DepthSaveValues,
    DepthUpdate,
    Hit,
    InputAnsweredData,
    InputNeededData,
    Page,
    Pause,
    ProfileUpdate,
    Question,
    QuestionOption,
    QuestionsAnswered,
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
    WritingOptions,
)
from wosarcher.store import RunStore, RunStoreError, new_run_id, presets
from wosarcher.store.caches import EmbeddingCache, PageCache
from wosarcher.store.presets import PresetError

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
    run_id = create(store, settings=Settings(score=ScoreConfig(provider="jev", api_key=SecretStr("sk-secret"))))
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
        store.append_event(run_id, "run.queued", None, RunQueuedData(position=0, limit=1))
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


def test_status_from_run_lock(store: RunStore) -> None:
    """With no terminal event, a run whose lock is held is `running`; a terminal event wins over the lock."""
    record = store.create(RunRequest(query="q"), "p", [], Settings(), [], lock=True)
    assert store.status(record.run_id) == "running"
    assert store.summary(record).status == "running"
    store.append_event(record.run_id, "run.done", None, RunDoneData(until=None, totals=UsageTotals()))
    assert store.status(record.run_id) == "done"
    assert RunStore(store.runs_dir, store.cache_dir).status(create(store)) == "interrupted"


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
    store.append_event(run_id, "run.queued", None, RunQueuedData(position=0, limit=1))
    append_raw(store, run_id, "not json\n")
    append_raw(store, run_id, '{"seq": 2, "run_id": "r", "ts": "2026-01-01T00:00:00Z", "type": "stage.paused"}\n')
    store.append_event(run_id, "run.queued", None, RunQueuedData(position=0, limit=1))
    assert [e.seq for e in store.read_events(run_id)] == [1, 2]


def nine_and_half(store: RunStore) -> str:
    run_id = create(store)
    for _ in range(9):
        store.append_event(run_id, "run.queued", None, RunQueuedData(position=0, limit=1))
    append_raw(store, run_id, '{"seq": 10, "run_id": "r", "ts": "2026-01')
    return run_id


def test_tail_seq_ignores_partial_line(store: RunStore) -> None:
    assert store.tail_seq(nine_and_half(store)) == 9


def test_tail_seq_long_line(store: RunStore) -> None:
    run_id = create(store)
    store.append_event(run_id, "run.queued", None, RunQueuedData(position=0, limit=1))
    store.append_event(run_id, "run.failed", None, RunFailedData(stage=None, error="x" * 21000))
    assert store.tail_seq(run_id) == 2


def test_seq_across_two_stores(store: RunStore) -> None:
    run_id = create(store)
    other = RunStore(store.runs_dir, store.cache_dir)
    seqs = [
        s.append_event(run_id, "run.queued", None, RunQueuedData(position=0, limit=1)).seq
        for s in (store, other, store)
    ]
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
    settings = Settings(plan=PlanConfig(max_sub_queries=6), write=WritingOptions(words=800))
    request = RunRequest(query="battery recycling", depth="deep")
    run_id = store.create(request, "workstation", overrides, settings, []).run_id
    saved = json.loads((store.run_dir(run_id) / "request.json").read_text())
    assert saved["request"]["depth"] == "deep"
    assert saved["overrides"] == ["write.words=800"]
    assert saved["settings"]["plan"]["max_sub_queries"] == 6
    assert store.list_runs()[0].depth == "deep"


def test_fork_keeps_depth(store: RunStore) -> None:
    run_id = store.create(RunRequest(query="q", depth="quick"), "workstation", [], Settings(), []).run_id
    finish(store, run_id, *STAGES[:-1])
    record = store.fork(run_id, "write", [], Settings())
    assert record.request.depth == "quick"


# Saved profiles and depth presets


@pytest.fixture
def preset_env(tmp_path: Path) -> dict[str, str]:
    """The minimal configuration plus a `cloud` profile on an `openrouter` entry."""
    env = {"XDG_CONFIG_HOME": str(tmp_path / "config")}
    root = tmp_path / "config" / "wosarcher"
    write_config(root, MINIMAL_CONFIG)
    write_config(
        root,
        {
            "providers/llm/openrouter.toml": 'provider = "openai"\nbase_url = "http://or.test/v1"\nmodel = "x"\n',
            "providers/score/rerank.toml": 'provider = "rerank"\nbase_url = "http://rr.test/v1"\n',
            "profiles/cloud.toml": 'description = "Hosted models."\n[use]\nprefilter = "bm25"\nllm = "openrouter"\n'
            '[llm]\nmodel = "claude-sonnet-5-5"\n[search]\nlanguage = "es"\n[run]\ngpu_policy = "exclusive"\n',
        },
    )
    return env


def preset_dir(env: dict[str, str]) -> Path:
    return Path(env["XDG_CONFIG_HOME"]) / "wosarcher"


DEPTH = DepthUpdate(
    description="Your preset: 10 sub-queries, 1 round, 1,500 words.",
    values=DepthSaveValues(
        sub_queries=10,
        results_per_query=12,
        max_pages=200,
        passages_per_query=8,
        rounds=1,
        queries_per_round=3,
        words=1500,
    ),
)


def test_path_in_a_name(preset_env: dict[str, str]) -> None:
    with pytest.raises(PresetError) as error:
        presets.save_profile("../x", "cloud", ProfileUpdate(), preset_env)
    assert error.value.code == "invalid_name"
    assert not (preset_dir(preset_env) / "x.toml").exists()


def test_reserved_depth_name(preset_env: dict[str, str]) -> None:
    with pytest.raises(PresetError, match="'Deep' is reserved") as error:
        presets.save_depth("Deep", DEPTH, preset_env)
    assert error.value.code == "invalid_name"


def test_taken_ignoring_case(preset_env: dict[str, str]) -> None:
    with pytest.raises(PresetError, match="'cloud'") as error:
        presets.save_profile("Cloud", "cloud", ProfileUpdate(), preset_env)
    assert error.value.code == "name_taken"


def test_saved_mode(preset_env: dict[str, str]) -> None:
    previous = os.umask(0o022)
    try:
        presets.save_profile("cloud-rerank", "cloud", ProfileUpdate(), preset_env)
    finally:
        os.umask(previous)
    assert (preset_dir(preset_env) / "profiles/cloud-rerank.toml").stat().st_mode & 0o777 == 0o600


def test_save_as_with_model_tuning(preset_env: dict[str, str]) -> None:
    edits = ProfileUpdate.model_validate(
        {"use": {"score": "rerank"}, "llm": {"reasoning": {"write": "high"}, "context_tokens": 120000}}
    )
    presets.save_profile("cloud-rerank", "cloud", edits, preset_env)
    profile = read_profile("cloud-rerank", preset_env)
    assert profile.description == "Hosted models."
    assert profile.use == {"prefilter": "bm25", "llm": "openrouter", "score": "rerank"}
    assert profile.data["select"]["max_context_tokens"] == 120000
    assert profile.models == {"claude-sonnet-5-5": {"reasoning": {"write": "high"}}}
    assert resolve("cloud-rerank", [], preset_env).llm.reasoning.write == "high"


def test_base_keys_kept(preset_env: dict[str, str]) -> None:
    presets.save_profile("copy", "cloud", ProfileUpdate(), preset_env)
    data = read_profile("copy", preset_env).data
    assert (data["search"]["language"], data["run"]["gpu_policy"]) == ("es", "exclusive")


def test_tuning_for_entry_default_model(preset_env: dict[str, str]) -> None:
    edits = ProfileUpdate.model_validate({"llm": {"max_output_tokens": 12288}})
    (preset_dir(preset_env) / "profiles/local.toml").write_text('[use]\nllm = "agents"\n')
    presets.update_profile("local", edits, preset_env)
    assert read_profile("local", preset_env).models == {"qwen3-14b": {"max_output_tokens": 12288}}


def test_save_edits_into_the_profile(preset_env: dict[str, str]) -> None:
    root = preset_dir(preset_env)
    (root / "profiles/low-vram.toml").write_text('[use]\nprefilter = "bm25"\n[llm]\nmodel = "qwen3-14b"\n')
    presets.update_profile("low-vram", ProfileUpdate.model_validate({"llm": {"max_output_tokens": 12288}}), preset_env)
    profile = read_profile("low-vram", preset_env)
    assert profile.models == {"qwen3-14b": {"max_output_tokens": 12288}}
    assert (profile.use, profile.data) == ({"prefilter": "bm25"}, {"llm": {"model": "qwen3-14b"}})


def test_update_a_managed_profile(preset_env: dict[str, str]) -> None:
    root = preset_dir(preset_env)
    (root / "profiles/.nix-managed").write_text("workstation.toml\n")
    before = (root / "profiles/workstation.toml").read_text()
    with pytest.raises(PresetError) as error:
        presets.update_profile("workstation", ProfileUpdate(description="x"), preset_env)
    assert error.value.code == "managed"
    assert (root / "profiles/workstation.toml").read_text() == before


def test_save_as_from_a_managed_profile(preset_env: dict[str, str]) -> None:
    (preset_dir(preset_env) / "profiles/.nix-managed").write_text("workstation.toml\n")
    presets.save_profile("ws-fast", "workstation", ProfileUpdate(), preset_env)
    assert (preset_dir(preset_env) / "profiles/ws-fast.toml").exists()


def test_active_profile_not_deleted(preset_env: dict[str, str]) -> None:
    store_profile("cloud", preset_env)
    with pytest.raises(PresetError) as error:
        presets.delete_profile("cloud", preset_env)
    assert error.value.code == "active_profile"
    assert (preset_dir(preset_env) / "profiles/cloud.toml").exists()


def test_save_a_depth(preset_env: dict[str, str]) -> None:
    presets.save_depth("wide", DEPTH, preset_env)
    depth, description, data = read_depth("wide", preset_env)
    assert (depth.source, description) == ("user", DEPTH.description)
    assert data == {
        "plan": {"max_sub_queries": 10},
        "search": {"max_results": 12},
        "fetch": {"max_pages": 200},
        "score": {"top_k": 8},
        "research": {"rounds": 1, "queries_per_round": 3},
        "write": {"words": 1500},
    }
    presets.replace_depth("wide", DepthUpdate(values=DEPTH.values.model_copy(update={"words": None})), preset_env)
    assert "write" not in read_depth("wide", preset_env)[2]
    presets.delete_depth("wide", preset_env)
    assert "wide" not in list_depths(preset_env)


def test_update_a_builtin_depth(preset_env: dict[str, str]) -> None:
    with pytest.raises(PresetError) as error:
        presets.replace_depth("quick", DEPTH, preset_env)
    assert error.value.code == "builtin"
    assert read_depth("quick", preset_env)[0].source == "builtin"


def test_delete_a_managed_depth(preset_env: dict[str, str]) -> None:
    presets.save_depth("wide", DEPTH, preset_env)
    (preset_dir(preset_env) / "profiles/.nix-managed").write_text("../depths/wide.toml\n")
    with pytest.raises(PresetError) as error:
        presets.delete_depth("wide", preset_env)
    assert error.value.code == "managed"
    assert read_depth("wide", preset_env)[0].name == "wide"


# Catalog runs


async def finished_catalog(tmp_path: Path) -> tuple["RunStore", str, "Settings"]:
    from tests.runner.test_catalog import world

    store, runner, run_id, _fakes = world(tmp_path)
    assert await runner.run(run_id) == "done"
    return store, run_id, runner.settings


async def test_catalog_request_record(tmp_path: Path) -> None:
    from wosarcher.models import RunRecord

    store, run_id, _ = await finished_catalog(tmp_path)
    data = json.loads((store.run_dir(run_id) / "request.json").read_text())
    assert data["request"]["kind"] == "catalog"
    assert data["request"]["structure"]["relation"] == "organismos adscritos"
    del data["request"]["kind"]
    del data["request"]["structure"]
    assert RunRecord.model_validate(data).kind == "research"


async def test_catalog_fork_from_extract(tmp_path: Path) -> None:
    from tests.runner.helpers import adapters
    from tests.runner.test_catalog import CatalogLLM
    from wosarcher.adapters.fakes import FakeFetcher, FakeSearcher
    from wosarcher.http import UsageLedger
    from wosarcher.models import CatalogRecord, Node
    from wosarcher.runner import Runner

    store, run_id, settings = await finished_catalog(tmp_path)
    fork = store.fork(run_id, "extract", ["use.llm=sonnet"], settings)
    path = store.run_dir(fork.run_id)
    assert (fork.kind, fork.fork_from) == ("catalog", "extract")
    assert (path / "nodes.jsonl").is_file()
    assert (path / "pages.jsonl").is_file()
    assert not (path / "records.jsonl").exists()
    assert {node.status for node in store.read_items(fork.run_id, "nodes.jsonl", Node)} == {"discovered"}
    searcher, fetcher, llm = FakeSearcher({}), FakeFetcher({}), CatalogLLM()
    fakes = adapters(searcher=searcher, fetcher=fetcher, planner=llm)
    assert await Runner(store, settings, fakes, UsageLedger({})).run(fork.run_id) == "done"
    assert searcher.calls == []
    assert fetcher.calls == []
    assert sorted(llm.names) == ["INEI", "MEF", "PCM", "Poder Ejecutivo"]
    assert len(store.read_artifact(fork.run_id, "catalog.json", CatalogRecord).records) == 4


async def test_catalog_fork_from_expand(tmp_path: Path) -> None:
    from tests.runner.helpers import adapters
    from tests.runner.test_catalog import PAGES, SEARCH, CatalogLLM
    from wosarcher.adapters.fakes import FakeFetcher, FakeSearcher
    from wosarcher.http import UsageLedger
    from wosarcher.models import Node, Structure, WaveDone
    from wosarcher.runner import Runner

    store, run_id, settings = await finished_catalog(tmp_path)
    with pytest.raises(RunStoreError, match="--max-depth"):
        store.fork(run_id, "expand", [], settings)
    with pytest.raises(RunStoreError, match="cannot lower"):
        store.fork(run_id, "expand", [], settings, limits={"max_depth": 1})
    fork = store.fork(run_id, "expand", ["catalog.max_depth=3"], settings, limits={"max_depth": 3})
    assert store.read_artifact(fork.run_id, "structure.json", Structure).limits.max_depth == 3
    found = {node.id: node for node in store.read_items(fork.run_id, "nodes.jsonl", Node)}
    assert found["inei"].status == "discovered"
    assert found["mef"].status == "extracted"
    llm = CatalogLLM()
    fakes = adapters(searcher=FakeSearcher(SEARCH), fetcher=FakeFetcher(PAGES), planner=llm)
    assert await Runner(store, settings, fakes, UsageLedger({})).run(fork.run_id) == "done"
    assert llm.names == ["INEI"]
    waves = [e.data.wave for e in store.read_events(fork.run_id) if isinstance(e, WaveDone)]
    assert waves == [1, 2, 3, 4]


async def test_catalog_fork_from_fetch_rejected(tmp_path: Path) -> None:
    store, run_id, settings = await finished_catalog(tmp_path)
    with pytest.raises(RunStoreError, match="expand or extract"):
        store.fork(run_id, "fetch", [], settings)


async def test_catalog_files_by_output(tmp_path: Path) -> None:
    from tests.runner.test_catalog import world
    from tests.stages.catalog_data import structure

    store, runner, run_id, _ = world(tmp_path / "table")
    assert await runner.run(run_id) == "done"
    names = {path.name for path in store.run_dir(run_id).iterdir()}
    assert {"structure.json", "nodes.jsonl", "records.jsonl", "catalog.json", "plan.json", "costs.json"} <= names
    assert names.isdisjoint({"report.md", "report.json", "context.json", "select.jsonl", "scores.jsonl"})
    store, runner, run_id, _ = world(tmp_path / "both", structure(limits={"max_depth": 2}, output="both"))
    assert await runner.run(run_id) == "done"
    names = {path.name for path in store.run_dir(run_id).iterdir()}
    assert {"context.json", "report.md", "report.json", "catalog.json"} <= names
    assert "select.jsonl" not in names


def pausing(store: RunStore, lock: bool) -> str:
    """A run whose log ends with `input.needed`, holding its lock when `lock`."""
    record = store.create(RunRequest(query="q"), "p", [], Settings(), [], lock=lock)
    run_id = record.run_id
    question = Question(
        id="q1",
        text="Go on?",
        kind="confirm",
        options=[QuestionOption(id="a", label="Yes", recommended=True), QuestionOption(id="b", label="No")],
    )
    created = datetime.now(UTC)
    pause = Pause(id=1, kind="round", after=1, questions=[question], created=created, timeout=60, max_wait=1800)
    store.write_pause(run_id, pause)
    needed = InputNeededData(
        pause_id=1, kind="round", after=1, questions=[question], created=created, timeout=60, max_wait=1800
    )
    store.append_event(run_id, "input.needed", "gap", needed)
    return run_id


def test_waiting_status_and_pending(store: RunStore) -> None:
    run_id = pausing(store, lock=True)
    summary = store.summary(store.read_record(run_id))
    assert summary.status == "waiting"
    assert summary.pending is not None
    assert (summary.pending.id, summary.pending.kind, summary.pending.after, summary.pending.questions) == (
        1,
        "round",
        1,
        1,
    )
    answered = InputAnsweredData(
        pause_id=1, answers=[Answer(question_id="q1", option_ids=["a"])], answered_by="user", seconds_waited=3
    )
    store.append_event(run_id, "input.answered", "gap", answered)
    assert store.summary(store.read_record(run_id)).status == "running"
    assert store.summary(store.read_record(run_id)).pending is None


def test_killed_while_waiting_is_interrupted(store: RunStore) -> None:
    run_id = pausing(RunStore(store.runs_dir, store.cache_dir), lock=False)
    assert store.summary(store.read_record(run_id)).status == "interrupted"


def test_deadline_follows_presence(store: RunStore) -> None:
    run_id = pausing(store, lock=True)
    open_pause = store.open_pause(run_id)
    assert open_pause is not None
    created = open_pause.created.timestamp()
    assert abs(open_pause.deadline.timestamp() - (created + 60)) < 0.01
    store.touch_hold(run_id, 1)
    os.utime(store.input_dir(run_id) / "1.hold", (created + 30, created + 30))
    moved = store.open_pause(run_id)
    assert moved is not None
    assert abs(moved.deadline.timestamp() - (created + 90)) < 0.01
    os.utime(store.input_dir(run_id) / "1.hold", (created + 5000, created + 5000))
    capped = store.open_pause(run_id)
    assert capped is not None
    assert abs(capped.deadline.timestamp() - (created + 1800)) < 0.01


def test_pause_files_listed(store: RunStore) -> None:
    run_id = pausing(store, lock=True)
    store.write_answer(
        run_id, 1, QuestionsAnswered(answers=[Answer(question_id="q1", option_ids=["a"])], answered_by="user")
    )
    names = sorted(path.name for path in store.input_dir(run_id).iterdir())
    assert names == ["1.answer.json", "1.json"]
    assert [pause.id for pause in store.read_pauses(run_id)] == [1]

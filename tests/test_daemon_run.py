"""`wosarcher run`, `fork`, and `runs` with fake adapters injected in place of `build.build`."""

import io
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

import wosarcher.build as building
from tests.fixtures.config import MINIMAL_CONFIG, write_config
from tests.runner.helpers import adapters
from wosarcher.adapters.fakes import FakeLLM, FakeSearcher
from wosarcher.cli.progress import ProgressView
from wosarcher.config import Settings
from wosarcher.daemon import app
from wosarcher.http import UsageLedger
from wosarcher.models import (
    Event,
    GapReadyData,
    ResearchDoneData,
    RunRecord,
    Stage,
    StageStartedData,
    make_event,
)
from wosarcher.ports import Adapters
from wosarcher.store import RunStore

runner = CliRunner()


class World:
    def __init__(self) -> None:
        self.built: list[Settings] = []
        self.fakes: list[Adapters] = []

    def build(self, settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        self.built.append(settings)
        self.fakes.append(adapters())
        return self.fakes[-1]


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    for name in ("WOSARCHER_PROFILE", "WOSARCHER_SCORE__API_KEY", "WOSARCHER_LLM__API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    write_config(tmp_path / "config" / "wosarcher", MINIMAL_CONFIG)
    fake = World()
    monkeypatch.setattr(building, "build", fake.build)
    return fake


def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "data" / "wosarcher" / "runs"


def only_run(tmp_path: Path) -> RunRecord:
    (path,) = [path for path in runs_dir(tmp_path).iterdir() if not path.name.startswith(".")]
    return RunRecord.model_validate_json((path / "request.json").read_text())


def test_writing_flags(world: World, tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["run", "battery recycling", "--set", "write.tone=objective", "--tone", "critical", "--words", "500"]
    )
    assert result.exit_code == 0, result.output
    assert (world.built[0].write.tone, world.built[0].write.words) == ("critical", 500)
    record = only_run(tmp_path)
    assert record.overrides == ["write.tone=objective", 'write.tone="critical"', "write.words=500"]
    assert "## References" in result.stdout


def test_format_flag(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "battery recycling", "--format", "answer"])
    assert result.exit_code == 0, result.output
    assert world.built[0].write.format == "answer"
    assert only_run(tmp_path).overrides == ['write.format="answer"']


def test_unknown_format(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--format", "summary"])
    assert result.exit_code == 2
    assert "--format" in result.output
    assert "report, answer" in result.output
    assert not runs_dir(tmp_path).exists()


def test_rounds_flag(world: World) -> None:
    result = runner.invoke(app, ["run", "battery recycling", "--depth", "deep", "--rounds", "2"])
    assert result.exit_code == 0, result.output
    assert world.built[0].research.rounds == 2


def test_depth_with_research_flag(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "battery recycling", "--depth", "deep", "--max-pages", "80"])
    assert result.exit_code == 0, result.output
    settings = world.built[0]
    assert (settings.fetch.max_pages, settings.plan.max_sub_queries) == (80, 6)
    record = only_run(tmp_path)
    assert (record.request.depth, record.overrides) == ("deep", ["fetch.max_pages=80"])


def test_auto_context_flag(world: World) -> None:
    args = ["run", "q", "--set", "select.max_context_tokens=12000", "--context-tokens", "auto"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert world.built[0].select.max_context_tokens == "auto"


def test_gap_context_flag(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--depth", "deep", "--gap-context-tokens", "auto"])
    assert result.exit_code == 0, result.output
    assert world.built[0].research.gap_context_tokens == "auto"
    assert only_run(tmp_path).overrides == ["research.gap_context_tokens=auto"]


def test_domain_flags(world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_SEARCH__ALLOW_DOMAINS", '["gob.pe"]')
    args = ["run", "q", "--until", "search", "--allow-domain", "sunat.gob.pe", "--allow-domain", "sbs.gob.pe"]
    result = runner.invoke(app, [*args, "--block-domain", "facebook.com"])
    assert result.exit_code == 0, result.output
    search = world.built[0].search
    assert (search.allow_domains, search.block_domains) == (["sunat.gob.pe", "sbs.gob.pe"], ["facebook.com"])
    assert only_run(tmp_path).overrides == [
        'search.allow_domains=["sunat.gob.pe", "sbs.gob.pe"]',
        'search.block_domains=["facebook.com"]',
    ]


def test_invalid_domain_flag(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--allow-domain", "https://gob.pe/x"])
    assert result.exit_code == 2
    assert "--allow-domain" in result.output
    assert "https://gob.pe/x" in result.output
    assert not runs_dir(tmp_path).exists()


def test_queries_per_round_flag(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--depth", "deep", "--queries-per-round", "6"])
    assert result.exit_code == 0, result.output
    assert world.built[0].research.queries_per_round == 6
    assert only_run(tmp_path).overrides == ["research.queries_per_round=6"]


def test_search_language_flag(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--until", "search", "--search-language", "es-PE"])
    assert result.exit_code == 0, result.output
    assert world.built[0].search.language == "es-PE"
    assert only_run(tmp_path).overrides == ['search.language="es-PE"']


def test_model_flag(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--model", "deepseek-v4-flash"])
    assert result.exit_code == 0, result.output
    assert world.built[0].llm.model == "deepseek-v4-flash"
    assert only_run(tmp_path).overrides == ['llm.model="deepseek-v4-flash"']


def test_thinking_flags(world: World, tmp_path: Path) -> None:
    args = ["run", "q", "--set", 'llm.reasoning.write="low"', "--write-thinking", "high", "--gap-thinking", "low"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    reasoning = world.built[0].llm.reasoning
    assert (reasoning.plan, reasoning.gap, reasoning.write) == ("none", "low", "high")
    assert only_run(tmp_path).overrides[-2:] == ['llm.reasoning.gap="low"', 'llm.reasoning.write="high"']


def test_invalid_thinking_level(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--plan-thinking", "max"], env={"COLUMNS": "200"})
    assert result.exit_code == 2
    assert "--plan-thinking" in result.output
    assert "none, low, medium, high, default" in result.output
    assert not runs_dir(tmp_path).exists()


def test_invalid_search_language(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--search-language", "spanish please"])
    assert result.exit_code == 2
    assert "--search-language" in result.output
    assert not runs_dir(tmp_path).exists()


def test_invalid_language_through_set(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--set", 'search.language="spanish"'])
    assert result.exit_code == 2
    assert "search.language" in result.output
    assert not runs_dir(tmp_path).exists()


def test_token_budget_flag_rejects_words(world: World) -> None:
    result = runner.invoke(app, ["run", "q", "--context-tokens", "all"])
    assert result.exit_code == 2


def test_files_without_attach(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--sources", "files"])
    assert result.exit_code == 2
    assert "--sources files needs --attach" in result.output
    assert not runs_dir(tmp_path).exists()


def test_unknown_until(world: World) -> None:
    result = runner.invoke(app, ["run", "q", "--until", "rank"])
    assert result.exit_code == 2
    assert "load, plan, search, fetch, chunk, prefilter, score, gap, select, write" in result.output


def test_invalid_override(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--set", "score.topk=3"])
    assert result.exit_code == 2
    assert not runs_dir(tmp_path).exists()


def test_json_until_select(world: World) -> None:
    result = runner.invoke(app, ["run", "battery recycling", "--until", "select", "--json"])
    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    assert document["status"] == "done"
    assert document["report"] is None
    assert document["context"]["passages"][0]["n"] == 1
    assert document["context"]["sources"]


def test_json_failed_fetch(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_pages(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        from wosarcher.adapters.fakes import FakeFetcher

        return adapters(fetcher=FakeFetcher())

    monkeypatch.setattr(building, "build", no_pages)
    result = runner.invoke(app, ["run", "battery recycling", "--sources", "web", "--json"])
    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert (document["status"], document["error"]) == ("failed", "no output")


def test_run_id_option(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "battery recycling", "--run-id", "20260101-120000-abcdef", "--until", "plan"])
    assert result.exit_code == 0, result.output
    assert (runs_dir(tmp_path) / "20260101-120000-abcdef" / "request.json").is_file()


def test_run_id_exists_fails(world: World, tmp_path: Path) -> None:
    taken = runs_dir(tmp_path) / "20260101-120000-abcdef"
    taken.mkdir(parents=True)
    (taken / "keep.txt").write_text("x")
    result = runner.invoke(app, ["run", "q", "--run-id", "20260101-120000-abcdef"])
    assert result.exit_code == 2
    assert [path.name for path in taken.iterdir()] == ["keep.txt"]


def test_piped_output_is_report(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "battery recycling"])
    assert result.exit_code == 0
    report = (runs_dir(tmp_path) / only_run(tmp_path).run_id / "report.md").read_text()
    assert result.stdout == report


def test_progress_view_replays_events(world: World, tmp_path: Path) -> None:
    assert runner.invoke(app, ["run", "battery recycling"]).exit_code == 0
    store = RunStore(runs_dir(tmp_path), tmp_path / "cache")
    from rich.console import Console

    view = ProgressView(Console(file=open(os.devnull, "w"), force_terminal=True))  # noqa: SIM115
    with view:
        for event in store.read_events(only_run(tmp_path).run_id):
            view(event)
    assert view.rows["write"].state == "done"


def round_event(event_type: str, stage: Stage, data: BaseModel) -> Event:
    return make_event(1, "r", datetime.now(UTC), event_type, stage, data)


def test_multi_round_progress() -> None:
    from rich.console import Console

    out = io.StringIO()
    view = ProgressView(Console(file=out, force_terminal=False, width=200), rounds=3)
    view.update(round_event("stage.started", "fetch", StageStartedData(device=None, provider="firecrawl", round=2)))
    assert view.rows["fetch"].state == "running · round 2/3"
    view.update(
        round_event("gap.ready", "gap", GapReadyData(round=1, queries=[], note="", uncovered=["q4"], retried=True))
    )
    assert view.rows["gap"].counters == "0 follow-ups, 1 uncovered"
    done = ResearchDoneData(planned=3, ran=1, reason="no follow-ups", note="")
    view.update(round_event("research.done", "gap", done))
    assert "research: 1 of 3 rounds · no follow-ups" in out.getvalue()
    assert "gap" not in ProgressView(Console(file=io.StringIO())).rows


def test_fork_rewrite_only(world: World, tmp_path: Path) -> None:
    assert runner.invoke(app, ["run", "battery recycling"]).exit_code == 0
    parent = only_run(tmp_path)
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "write", "--tone", "critical"])
    assert result.exit_code == 0, result.output
    fork = next(r for r in RunStore(runs_dir(tmp_path), tmp_path).list_runs() if r.run_id != parent.run_id)
    record = RunStore(runs_dir(tmp_path), tmp_path).read_record(fork.run_id)
    assert (record.version, record.fork_from, record.parent_run_id) == (2, "write", parent.run_id)
    fakes = world.fakes[-1]
    assert isinstance(fakes.planner, FakeLLM)
    assert isinstance(fakes.writer, FakeLLM)
    assert isinstance(fakes.searcher, FakeSearcher)
    assert (fakes.planner.calls, fakes.searcher.calls) == ([], [])
    assert len(fakes.writer.calls) == 1
    assert world.built[-1].write.tone == "critical"


def test_fork_keeps_thinking(world: World, tmp_path: Path) -> None:
    assert runner.invoke(app, ["run", "battery recycling", "--write-thinking", "high"]).exit_code == 0
    parent = only_run(tmp_path)
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "write", "--tone", "critical"])
    assert result.exit_code == 0, result.output
    assert world.built[-1].llm.reasoning.write == "high"
    writer = world.fakes[-1].writer
    assert isinstance(writer, FakeLLM)
    assert writer.efforts == ["high"]


def test_fork_as_answer(world: World, tmp_path: Path) -> None:
    assert runner.invoke(app, ["run", "battery recycling"]).exit_code == 0
    parent = only_run(tmp_path)
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "write", "--format", "answer"])
    assert result.exit_code == 0, result.output
    store = RunStore(runs_dir(tmp_path), tmp_path)
    fork = next(r for r in store.list_runs() if r.run_id != parent.run_id)
    assert store.read_record(fork.run_id).overrides == ['write.format="answer"']
    fakes = world.fakes[-1]
    assert isinstance(fakes.planner, FakeLLM)
    assert isinstance(fakes.writer, FakeLLM)
    assert (fakes.planner.calls, len(fakes.writer.calls)) == ([], 1)
    assert world.built[-1].write.format == "answer"


def config(tmp_path: Path, files: dict[str, str]) -> None:
    write_config(tmp_path / "config" / "wosarcher", files)


JEV = 'provider = "jev"\nbase_url = "http://jev.test"\napi_key = "tk"\n'


def test_entries_recorded(world: World, tmp_path: Path) -> None:
    config(tmp_path, {"providers/score/jev-strict.toml": JEV, "profiles/workstation.toml": BASE_USE})
    result = runner.invoke(app, ["run", "q", "--use", "score=jev-strict", "--until", "plan"])
    assert result.exit_code == 0, result.output
    record = only_run(tmp_path)
    assert record.profile == "workstation"
    assert record.use == {
        "search": "searxng",
        "fetch": "firecrawl",
        "prefilter": "bm25",
        "score": "jev-strict",
        "llm": "agents",
    }
    assert record.overrides == ["use.score=jev-strict"]
    assert world.built[0].score.provider == "jev"


def test_unknown_entry(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--use", "llm=sonet"])
    assert result.exit_code == 2
    assert "unknown llm entry 'sonet'; llm entries: agents" in result.output
    assert not runs_dir(tmp_path).exists()


def test_unknown_block_in_use(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--use", "scorer=bm25"], env={"COLUMNS": "200"})
    assert result.exit_code == 2
    assert "--use" in result.output
    assert "unknown block 'scorer'; choose from search, fetch, prefilter, score, llm" in result.output


BASE_USE = '[use]\nprefilter = "bm25"\nscore = "bm25"\nllm = "agents"\n'
SONNET = 'provider = "openai"\nbase_url = "http://sonnet.test/v1"\nmodel = "sonnet"\n'
OMNIROUTE = (
    'provider = "openai"\nbase_url = "http://omni.test/v1"\nmodel = "smart"\n[models.smart]\ncontext_window = 1048576\n'
)


def sonnet_parent(tmp_path: Path) -> RunRecord:
    config(tmp_path, {"providers/llm/sonnet.toml": SONNET, "profiles/workstation.toml": BASE_USE})
    assert runner.invoke(app, ["run", "q", "--use", "llm=sonnet"]).exit_code == 0
    return only_run(tmp_path)


def test_fork_entry_gone(world: World, tmp_path: Path) -> None:
    parent = sonnet_parent(tmp_path)
    (tmp_path / "config" / "wosarcher" / "providers" / "llm" / "sonnet.toml").unlink()
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "write"])
    assert result.exit_code == 2
    assert "unknown llm entry 'sonnet'; llm entries: agents" in result.output
    assert [path.name for path in runs_dir(tmp_path).iterdir() if not path.name.startswith(".")] == [parent.run_id]


def test_fork_entry_gone_replaced(world: World, tmp_path: Path) -> None:
    parent = sonnet_parent(tmp_path)
    (tmp_path / "config" / "wosarcher" / "providers" / "llm" / "sonnet.toml").unlink()
    config(tmp_path, {"providers/llm/omniroute.toml": OMNIROUTE})
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "write", "--use", "llm=omniroute"])
    assert result.exit_code == 0, result.output
    llm = world.built[-1].llm
    assert (llm.base_url, llm.model, llm.context_window) == ("http://omni.test/v1", "smart", 1048576)
    store = RunStore(runs_dir(tmp_path), tmp_path)
    fork = next(r for r in store.list_runs() if r.run_id != parent.run_id)
    assert store.read_record(fork.run_id).use == {**(parent.use or {}), "llm": "omniroute"}


def test_fork_retry_with_another_scorer(world: World, tmp_path: Path) -> None:
    config(tmp_path, {"providers/score/jev-strict.toml": JEV, "profiles/workstation.toml": BASE_USE})
    assert runner.invoke(app, ["run", "q", "--use", "score=jev-strict"]).exit_code == 0
    parent = only_run(tmp_path)
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "score", "--use", "score=bm25"])
    assert result.exit_code == 0, result.output
    assert world.built[-1].score.provider == "bm25"
    store = RunStore(runs_dir(tmp_path), tmp_path)
    fork = store.read_record(next(r.run_id for r in store.list_runs() if r.run_id != parent.run_id))
    assert (fork.use or {})["score"] == "bm25"
    assert fork.changes == ["use.score=bm25"]


def test_fork_ignores_saved_source(world: World, tmp_path: Path) -> None:
    assert runner.invoke(app, ["run", "q"]).exit_code == 0
    parent = only_run(tmp_path)
    path = runs_dir(tmp_path) / parent.run_id / "request.json"
    data = json.loads(path.read_text())
    data["settings"]["llm"] |= {"api_key": "***", "api_key_file": "/run/secrets/old"}
    path.write_text(json.dumps(data))
    agents = 'provider = "openai"\nbase_url = "http://llm.test/v1"\nmodel = "qwen3-14b"\napi_key = "sk-new"\n'
    config(tmp_path, {"providers/llm/agents.toml": agents})
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "write"])
    assert result.exit_code == 0, result.output
    api_key = world.built[-1].llm.api_key
    assert api_key is not None
    assert api_key.get_secret_value() == "sk-new"


def test_fork_with_profile(world: World, tmp_path: Path) -> None:
    config(
        tmp_path, {"providers/score/jev.toml": JEV, "profiles/cloud.toml": '[use]\nprefilter = "bm25"\nscore = "jev"\n'}
    )
    config(tmp_path, {"profiles/workstation.toml": '[use]\nprefilter = "bm25"\nscore = "bm25"\n'})
    assert runner.invoke(app, ["run", "battery recycling", "--until", "prefilter"]).exit_code == 0
    parent = only_run(tmp_path)
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "score", "--profile", "cloud", "--until", "score"])
    assert result.exit_code == 0, result.output
    assert world.built[-1].score.provider == "jev"
    store = RunStore(runs_dir(tmp_path), tmp_path)
    fork = next(r for r in store.list_runs() if r.run_id != parent.run_id)
    assert store.read_record(fork.run_id).profile == "cloud"


def stale_parent(tmp_path: Path, block: str, key: str, value: object) -> RunRecord:
    assert runner.invoke(app, ["run", "battery recycling"]).exit_code == 0
    parent = only_run(tmp_path)
    path = runs_dir(tmp_path) / parent.run_id / "request.json"
    data = json.loads(path.read_text())
    data["settings"][block][key] = value
    path.write_text(json.dumps(data))
    return parent


def test_fork_drops_stale_saved_key(world: World, tmp_path: Path) -> None:
    parent = stale_parent(tmp_path, "llm", "reasoning_tokens", 4096)
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "write"])
    assert result.exit_code == 0, result.output
    assert "warning: saved settings dropped: llm.reasoning_tokens" in result.stderr
    store = RunStore(runs_dir(tmp_path), tmp_path)
    fork = next(r for r in store.list_runs() if r.run_id != parent.run_id)
    assert "reasoning_tokens" not in store.read_record(fork.run_id).settings["llm"]


def test_fork_fails_on_stale_saved_value(world: World, tmp_path: Path) -> None:
    parent = stale_parent(tmp_path, "llm", "provider", "llm")
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "write"])
    assert result.exit_code == 2
    assert "llm.provider" in result.output


SLOW_RUN = """
import asyncio, sys
import wosarcher.build as building
from tests.fixtures.config import MINIMAL_CONFIG, write_config
from tests.runner.helpers import adapters
from wosarcher.adapters.fakes import FakeFetcher

class Slow(FakeFetcher):
    async def fetch(self, url):
        print("fetching", flush=True)
        await asyncio.sleep(30)

building.build = lambda settings, http, ledger: adapters(fetcher=Slow())
from wosarcher.daemon import app
app(["run", "battery recycling", "--run-id", "20260101-120000-abcdef"])
"""


def slow_run(tmp_path: Path) -> "subprocess.Popen[str]":
    """`wosarcherd run` in a subprocess, stopped in fetch."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("WOSARCHER_")}
    env |= {"XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CACHE_HOME": str(tmp_path / "cache")}
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    write_config(tmp_path / "config" / "wosarcher", MINIMAL_CONFIG)
    root = Path(__file__).resolve().parent.parent
    process = subprocess.Popen(
        [sys.executable, "-c", SLOW_RUN], cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    assert process.stdout is not None
    deadline = time.monotonic() + 20
    while process.stdout.readline().strip() != "fetching" and time.monotonic() < deadline:
        pass
    return process


def test_run_lock(tmp_path: Path) -> None:
    """The run is `running` while its process lives and `interrupted` once SIGKILL drops the lock."""
    process = slow_run(tmp_path)
    store = RunStore(runs_dir(tmp_path), tmp_path / "cache")
    try:
        assert store.status("20260101-120000-abcdef") == "running"
    finally:
        process.kill()
        process.wait(timeout=20)
    assert store.status("20260101-120000-abcdef") == "interrupted"


def test_sigterm_exits_130(tmp_path: Path) -> None:
    process = slow_run(tmp_path)
    process.send_signal(signal.SIGTERM)
    assert process.wait(timeout=20) == 130
    log = (runs_dir(tmp_path) / "20260101-120000-abcdef" / "events.jsonl").read_text().splitlines()
    last = json.loads(log[-1])
    assert (last["type"], last["data"]["stage"]) == ("run.cancelled", "fetch")


def test_stderr_diagnostics_when_piped(world: World, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "battery recycling"])
    assert result.exit_code == 0
    lines = result.stderr.splitlines()
    assert any(line.startswith("INFO ") and " plan stage.started " in line for line in lines)
    assert any(line.startswith("INFO ") and " plan stage.done " in line for line in lines)
    assert any(line.startswith("INFO ") and " run.done " in line for line in lines)


CATALOG_STRUCTURE = {
    "fields": [
        {"name": "id", "type": "slug"},
        {"name": "name", "type": "text", "required": True},
        {"name": "type", "type": "enum", "values": ["power", "agency"]},
    ],
    "relation": "organismos adscritos",
    "seeds": [{"name": "Poder Ejecutivo", "type": "power"}],
    "limits": {"max_depth": 2},
}


def test_catalog_run_flags(world: World, tmp_path: Path) -> None:
    args = ["run", "brief", "--kind", "catalog", "--structure", json.dumps(CATALOG_STRUCTURE), "--max-nodes", "7"]
    result = runner.invoke(app, [*args, "--until", "draft"])
    assert result.exit_code == 0, result.output
    record = only_run(tmp_path)
    assert record.kind == "catalog"
    assert record.structure is not None
    assert (record.structure.limits.max_depth, record.structure.limits.max_nodes) == (2, 7)
    assert record.structure.limits.pages_per_node == 2
    assert "catalog.max_nodes=7" in record.overrides


def test_catalog_run_rejections(world: World, tmp_path: Path) -> None:
    structure = json.dumps(CATALOG_STRUCTURE)
    bad = runner.invoke(app, ["run", "brief", "--kind", "catalog", "--structure", '{"fields": []}'])
    assert bad.exit_code == 2
    assert "--structure" in bad.output
    until = runner.invoke(app, ["run", "brief", "--kind", "catalog", "--structure", structure, "--until", "score"])
    assert until.exit_code == 2
    assert "assemble" in until.output
    research = runner.invoke(app, ["run", "q", "--structure", structure])
    assert research.exit_code == 2
    kind = runner.invoke(app, ["run", "q", "--kind", "atlas"])
    assert kind.exit_code == 2
    assert "--kind" in kind.output


def test_catalog_fork_limit_flags(world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.runner.test_catalog import CatalogLLM

    structure = json.dumps(CATALOG_STRUCTURE)

    def build(*_args: object) -> Adapters:
        return adapters(planner=CatalogLLM())

    monkeypatch.setattr(building, "build", build)
    first = runner.invoke(app, ["run", "brief", "--kind", "catalog", "--structure", structure, "--sources", "web"])
    assert first.exit_code == 0, first.output
    parent = only_run(tmp_path).run_id
    rejected = runner.invoke(app, ["fork", parent, "--from", "fetch"])
    assert rejected.exit_code == 2
    assert "expand or extract" in rejected.output
    same = runner.invoke(app, ["fork", parent, "--from", "expand"])
    assert same.exit_code == 2
    assert "--max-depth" in same.output
    raised = runner.invoke(app, ["fork", parent, "--from", "expand", "--max-depth", "3"])
    assert raised.exit_code == 0, raised.output
    forks = [
        RunRecord.model_validate_json((path / "request.json").read_text())
        for path in runs_dir(tmp_path).iterdir()
        if not path.name.startswith(".") and path.name != parent
    ]
    assert len(forks) == 1
    assert forks[0].structure is not None
    assert forks[0].structure.limits.max_depth == 3
    assert "catalog.max_depth=3" in forks[0].overrides

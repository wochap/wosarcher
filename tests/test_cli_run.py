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
from tests.runner.helpers import adapters
from wosarcher.adapters.fakes import FakeLLM, FakeSearcher
from wosarcher.cli import app
from wosarcher.cli.progress import ProgressView
from wosarcher.config import Settings
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
    fake = World()
    monkeypatch.setattr(building, "build", fake.build)
    return fake


def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "data" / "wosarcher" / "runs"


def only_run(tmp_path: Path) -> RunRecord:
    (path,) = runs_dir(tmp_path).iterdir()
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
    assert "search.allow_domains" in result.output
    assert "https://gob.pe/x" in result.output
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


def test_fork_with_profile(world: World, tmp_path: Path) -> None:
    assert runner.invoke(app, ["run", "battery recycling", "--until", "prefilter"]).exit_code == 0
    parent = only_run(tmp_path)
    result = runner.invoke(app, ["fork", parent.run_id, "--from", "score", "--profile", "cloud", "--until", "score"])
    assert result.exit_code == 0, result.output
    assert world.built[-1].score.provider == "jev"
    store = RunStore(runs_dir(tmp_path), tmp_path)
    fork = next(r for r in store.list_runs() if r.run_id != parent.run_id)
    assert store.read_record(fork.run_id).profile == "cloud"


def test_runs_json(world: World) -> None:
    for query in ("first", "second"):
        assert runner.invoke(app, ["run", query, "--until", "plan"]).exit_code == 0
    result = runner.invoke(app, ["runs", "--json"])
    assert result.exit_code == 0
    listed = json.loads(result.stdout)
    assert [(item["query"], item["status"]) for item in listed] == [("second", "done"), ("first", "done")]


SLOW_RUN = """
import asyncio, sys
import wosarcher.build as building
from tests.runner.helpers import adapters
from wosarcher.adapters.fakes import FakeFetcher

class Slow(FakeFetcher):
    async def fetch(self, url):
        print("fetching", flush=True)
        await asyncio.sleep(30)

building.build = lambda settings, http, ledger: adapters(fetcher=Slow())
from wosarcher.cli import app
app(["run", "battery recycling", "--run-id", "20260101-120000-abcdef"])
"""


def test_sigterm_exits_130(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("WOSARCHER_")}
    env |= {"XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CACHE_HOME": str(tmp_path / "cache")}
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    root = Path(__file__).resolve().parent.parent
    process = subprocess.Popen(
        [sys.executable, "-c", SLOW_RUN], cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    assert process.stdout is not None
    deadline = time.monotonic() + 20
    while process.stdout.readline().strip() != "fetching" and time.monotonic() < deadline:
        pass
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

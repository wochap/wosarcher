"""`wosarcher logs` and the event line format shared with the run process's standard error."""

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import Daemon, create_run
from wosarcher.cli import app
from wosarcher.cli.logs import event_line, stderr_listener
from wosarcher.config import Settings
from wosarcher.models import (
    CatalogDoneData,
    HitFoundData,
    NodeExtractedData,
    NodeFailedData,
    NodeFoundData,
    PageFailedData,
    RunDoneData,
    RunFailedData,
    RunRequest,
    RunStartedData,
    StageDoneData,
    StageFailedData,
    StageStartedData,
    UsageTotals,
    WaveDoneData,
    make_event,
)
from wosarcher.store import RunStore

TS = datetime(2026, 1, 1, 10, 2, 5, tzinfo=UTC)
runner = CliRunner()


@pytest.fixture(autouse=True)
def utc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()


def line(event_type: str, stage: str | None, data: object) -> str:
    return event_line(make_event(1, "r", TS, event_type, stage, data))  # pyright: ignore[reportArgumentType]


def test_run_started_line() -> None:
    data = RunStartedData(query="battery recycling", profile="p", parent_run_id=None, version=1, until=None)
    assert line("run.started", None, data) == "10:02:05 - run.started battery recycling"


def test_stage_done_line() -> None:
    data = StageDoneData(count=12, seconds=3.25, provider="firecrawl", copied_from="parent", warnings=["a", "b"])
    expected = "10:02:05 fetch stage.done count=12 3.2s provider=firecrawl copied from parent 2 warnings"
    assert line("stage.done", "fetch", data) == expected


def test_stage_failed_line() -> None:
    data = StageFailedData(error="timeout\nretry", next="")
    assert line("stage.failed", "score", data) == "10:02:05 score stage.failed timeout retry -> next=none"


def test_run_failed_line() -> None:
    data = RunFailedData(stage="fetch", error="no output")
    assert line("run.failed", "fetch", data) == "10:02:05 fetch run.failed fetch: no output"


def test_page_failed_long_reason() -> None:
    text = line("page.failed", "fetch", PageFailedData(url="https://x.test", reason="r" * 300))
    summary = text.split(" page.failed ", 1)[1]
    assert len(summary) <= 160
    assert summary.endswith("…")


def test_stderr_listener_levels(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("wosarcher.test")
    caplog.set_level(logging.INFO, logger="wosarcher.test")
    listen = stderr_listener(logger)
    listen(make_event(1, "r", TS, "stage.started", "fetch", StageStartedData(device=None, provider="firecrawl")))
    done = StageDoneData(count=12, seconds=1, warnings=["3 pages empty"])
    listen(make_event(2, "r", TS, "stage.done", "fetch", done))
    hit = HitFoundData(url="https://x.test", title="t", query_ids=["q1"])
    listen(make_event(3, "r", TS, "hit.found", "search", hit))
    listen(make_event(4, "r", TS, "run.failed", "fetch", RunFailedData(stage="fetch", error="no output")))
    records = [(r.levelname, r.getMessage().split(" ", 1)[1]) for r in caplog.records]
    assert records == [
        ("INFO", "fetch stage.started provider=firecrawl device=-"),
        ("INFO", "fetch stage.done count=12 1.0s provider=- 1 warnings"),
        ("WARNING", "fetch: 3 pages empty"),
        ("WARNING", "fetch run.failed fetch: no output"),
    ]


@pytest.fixture
def store(daemon: Daemon) -> RunStore:
    return RunStore(daemon.runs_dir, daemon.runs_dir)


def started(store: RunStore) -> str:
    run_id = store.create(RunRequest(query="q"), "p", [], Settings(), []).run_id
    data = RunStartedData(query="q", profile="p", parent_run_id=None, version=1, until=None)
    store.append_event(run_id, "run.started", None, data)
    return run_id


def types(output: str) -> list[str]:
    return [printed.split(" ")[2] for printed in output.splitlines()]


def finish(store: RunStore, run_id: str) -> None:
    store.append_event(run_id, "run.done", None, RunDoneData(until=None, totals=UsageTotals()))


def test_logs_finished_run(store: RunStore) -> None:
    run_id = started(store)
    store.append_event(run_id, "run.failed", "fetch", RunFailedData(stage="fetch", error="no output\nmore"))
    result = runner.invoke(app, ["logs", run_id])
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert types(result.stdout) == ["run.started", "run.failed"]
    assert lines[-1].endswith("fetch run.failed fetch: no output more")


def test_logs_unknown_run_exit_2(store: RunStore) -> None:
    result = runner.invoke(app, ["logs", "does-not-exist"])
    assert result.exit_code == 2
    assert "does-not-exist" in result.stderr


def test_logs_skips_bad_line(store: RunStore) -> None:
    run_id = started(store)
    with (store.run_dir(run_id) / "events.jsonl").open("a") as log:
        log.write("not json\n")
    finish(store, run_id)
    result = runner.invoke(app, ["logs", run_id])
    assert result.exit_code == 0
    assert types(result.stdout) == ["run.started", "run.done"]


def test_logs_follow(daemon: Daemon) -> None:
    """A run the server started, followed on the event socket until `run.done`."""
    run_id = create_run(daemon, "slow")
    result = runner.invoke(app, ["logs", run_id, "--follow"])
    assert result.exit_code == 0, result.output
    printed = types(result.stdout)
    assert printed[0] == "run.started"
    assert printed[-1] == "run.done"
    assert "stage.progress" in printed


def test_node_found_line() -> None:
    data = NodeFoundData(
        node_id="pcm", name="PCM", type="ministry", parent_id=None, depth=0, url=None, wave=1, found_by="seed"
    )
    assert line("node.found", "draft", data) == "10:02:05 draft node.found pcm depth 0 ← seed"
    child = data.model_copy(update={"node_id": "sgp", "parent_id": "pcm", "depth": 1})
    assert line("node.found", "extract", child).endswith("node.found sgp depth 1 ← pcm")


def test_node_extracted_line() -> None:
    data = NodeExtractedData(
        node_id="pcm", record={"name": "PCM", "head": None, "type": "ministry"}, flags=["x"], children=4
    )
    assert line("node.extracted", "extract", data).endswith("pcm 2 values · 4 children · 1 flags")


def test_node_failed_line() -> None:
    data = NodeFailedData(node_id="pcm", reason="no page")
    assert line("node.failed", "extract", data).endswith("node.failed pcm no page")


def test_wave_and_catalog_done_lines() -> None:
    wave = WaveDoneData(wave=1, expanded=6, found=14, records=6, failed=0, dropped=0)
    assert line("wave.done", "extract", wave).endswith("wave 1 expanded 6 found 14 records 6 failed 0")
    done = CatalogDoneData(waves=3, nodes=120, records=118, flagged=4, reason="frontier empty", note="")
    assert line("catalog.done", "assemble", done).endswith("3 waves · 118 records · 4 flagged · frontier empty")


def test_logs_of_a_catalog_run(daemon: Daemon, tmp_path: Path) -> None:
    from tests.stages.catalog_data import structure_data

    path = tmp_path / "s.json"
    path.write_text(json.dumps(structure_data()))
    assert runner.invoke(app, ["catalog", "b", "--structure", str(path)]).exit_code == 0
    [run_id] = [p.name for p in daemon.runs_dir.iterdir() if not p.name.startswith(".")]
    result = runner.invoke(app, ["logs", run_id])
    assert result.exit_code == 0
    assert any(
        " catalog.done 1 waves · 1 records · 0 flagged · frontier empty" in row for row in result.stdout.splitlines()
    )

"""`wosarcher logs` and the event line format shared with the run process's standard error."""

import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wosarcher.cli import app
from wosarcher.cli.logs import event_line, stderr_listener
from wosarcher.config import Settings
from wosarcher.models import (
    HitFoundData,
    PageFailedData,
    RunDoneData,
    RunFailedData,
    RunRequest,
    RunStartedData,
    StageDoneData,
    StageFailedData,
    StageStartedData,
    UsageTotals,
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
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunStore:
    for name in ("WOSARCHER_PROFILE", "WOSARCHER_RUN__RUNS_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return RunStore(tmp_path / "data" / "wosarcher" / "runs", tmp_path / "cache")


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


def test_logs_follow(store: RunStore) -> None:
    run_id = started(store)

    def later() -> None:
        time.sleep(0.2)
        store.append_event(run_id, "stage.done", "plan", StageDoneData(count=1, seconds=0.1))
        finish(store, run_id)

    thread = threading.Thread(target=later)
    thread.start()
    result = runner.invoke(app, ["logs", run_id, "--follow"])
    thread.join()
    assert result.exit_code == 0
    assert types(result.stdout) == ["run.started", "stage.done", "run.done"]

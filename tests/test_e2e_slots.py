"""`wosarcher run` and the shared run slots, with real processes and an offline files-only run."""

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.fixtures.recorded import NOTES, config_home
from wosarcher.config import Settings
from wosarcher.models import RunRequest, SlotEntry
from wosarcher.store import RunStore
from wosarcher.store.slots import Held

RUN = ["run", "q", "--profile", "e2e", "--sources", "files", "--attach", str(NOTES), "--until", "select"]


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunStore:
    for name in ("WOSARCHER_PROFILE", "WOSARCHER_SCORE__API_KEY", "WOSARCHER_LLM__API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home(tmp_path / "config")))
    monkeypatch.setenv("WOSARCHER_RUN__RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("WOSARCHER_RUN__CACHE_DIR", str(tmp_path / "cache"))
    return RunStore(tmp_path / "runs", tmp_path / "cache", tmp_path / "config" / "wosarcher")


def cli(*args: str) -> subprocess.Popen[str]:
    command = [sys.executable, "-m", "wosarcher", *args]
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())


def wait_until(condition: Callable[[], object], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.05)


def hold(store: RunStore, run_id: str = "holder") -> Held:
    held = store.slots.try_take(SlotEntry(run_id=run_id, origin="web"))
    assert held is not None
    return held


def event_types(store: RunStore, run_id: str) -> list[str]:
    return [event.type for event in store.read_events(run_id)]


def test_no_wait_without_a_free_slot(store: RunStore) -> None:
    held = hold(store)
    process = cli(*RUN, "--no-wait")
    _, err = process.communicate(timeout=30)
    held.close()
    assert process.returncode == 75
    assert "error: no free run slot (1 of 1 in use)" in err
    assert [path.name for path in store.runs_dir.iterdir()] == [".slots"]


def test_no_wait_with_a_free_slot(store: RunStore) -> None:
    process = cli(*RUN, "--no-wait", "--json")
    out, err = process.communicate(timeout=60)
    assert process.returncode == 0, err
    assert json.loads(out)["status"] == "done"


def test_waits_for_a_slot(store: RunStore) -> None:
    held = hold(store)
    process = cli(*RUN, "--json", "--run-id", "waiting")
    wait_until(lambda: store.slots.live("waiting") == "queued")
    assert store.status("waiting") == "queued"
    runs = subprocess.run([sys.executable, "-m", "wosarcher", "runs", "--json"], capture_output=True, text=True)
    listed = json.loads(runs.stdout)[0]
    assert (listed["status"], listed["queue_position"], listed["origin"]) == ("queued", 1, "cli")
    assert event_types(store, "waiting") == []
    held.close()
    out, err = process.communicate(timeout=60)
    assert process.returncode == 0, err
    assert "waiting for a free run slot (position 1)" in err
    assert json.loads(out)["status"] == "done"
    assert store.status("waiting") == "done"


def test_cancel_request_while_waiting(store: RunStore) -> None:
    held = hold(store)
    process = cli(*RUN, "--run-id", "waiting")
    wait_until(lambda: store.slots.live("waiting") == "queued")
    store.slots.request_cancel("waiting")
    process.communicate(timeout=30)
    held.close()
    assert process.returncode == 130
    assert event_types(store, "waiting") == ["run.cancelled"]
    assert store.slots.state().queued == []
    assert not store.slots.cancel_requested("waiting")


def test_sigint_while_waiting(store: RunStore) -> None:
    held = hold(store)
    process = cli(*RUN, "--run-id", "waiting")
    wait_until(lambda: store.slots.live("waiting") == "queued")
    process.send_signal(signal.SIGINT)
    process.communicate(timeout=30)
    held.close()
    assert process.returncode == 130
    assert event_types(store, "waiting")[-1] == "run.cancelled"


def test_killed_waiter_does_not_block(store: RunStore) -> None:
    held = hold(store)
    first = cli(*RUN, "--run-id", "first")
    wait_until(lambda: store.slots.live("first") == "queued")
    second = cli(*RUN, "--json", "--run-id", "second")
    wait_until(lambda: store.slots.position("second") == 2)
    first.kill()
    first.wait()
    assert store.status("first") == "interrupted"
    held.close()
    out, err = second.communicate(timeout=60)
    assert second.returncode == 0, err
    assert json.loads(out)["status"] == "done"


def test_live_cli_run_listed_as_running(store: RunStore) -> None:
    record = store.create(RunRequest(query="q"), "e2e", [], Settings(), [], "live")
    held = hold(store, "live")
    runs = subprocess.run([sys.executable, "-m", "wosarcher", "runs", "--json"], capture_output=True, text=True)
    held.close()
    listed = json.loads(runs.stdout)[0]
    assert (listed["run_id"], listed["status"], listed["origin"]) == (record.run_id, "running", "cli")
    assert store.status("live") == "interrupted"


def test_removed_concurrency_setting(store: RunStore) -> None:
    process = cli(*RUN, "--set", "server.max_concurrent_runs=2")
    _, err = process.communicate(timeout=30)
    assert process.returncode == 2
    assert "server.max_concurrent_runs" in err
    assert not store.runs_dir.exists()

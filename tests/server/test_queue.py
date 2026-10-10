import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import ANY

import pytest
from fastapi.testclient import TestClient

from tests.server.conftest import BASE_URL, MakeApp, argv, create, events, external, finished, status, wait_until
from wosarcher.auth import AuthStore
from wosarcher.models import SlotEntry
from wosarcher.server import staging
from wosarcher.server.manager import ENDED_LIMIT
from wosarcher.store import RunStore
from wosarcher.store.slots import Held


@pytest.fixture
def slow(runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_MODE", "slow")


def position(client: TestClient, run_id: str) -> int | None:
    return client.get(f"/api/runs/{run_id}").json()["queue_position"]


@pytest.mark.usefixtures("slow")
def test_second_run_waits(client: TestClient, runs_dir: Path) -> None:
    first, second = create(client, {"query": "q"}), create(client, {"query": "q"})
    assert status(client, first) == "running"
    assert (status(client, second), position(client, second)) == ("queued", 1)
    finished(client, first)
    wait_until(lambda: status(client, second) == "running")
    finished(client, second)
    assert events(runs_dir, second)[-1]["type"] == "run.done"
    assert not list(staging.queue_dir(runs_dir).glob("*"))


@pytest.mark.usefixtures("slow")
def test_two_slots(make_app: MakeApp) -> None:
    with TestClient(make_app(limit=2), base_url=BASE_URL) as client:
        runs = [create(client, {"query": "q"}) for _ in range(3)]
        assert [status(client, run_id) for run_id in runs] == ["running", "running", "queued"]
        assert position(client, runs[2]) == 1
        for run_id in runs:
            finished(client, run_id)


def test_crash_appends_run_failed(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, {"query": "crash"})
    finished(client, run_id)
    last = events(runs_dir, run_id)[-1]
    assert last["type"] == "run.failed"
    assert last["seq"] == events(runs_dir, run_id)[-2]["seq"] + 1
    assert "code 1" in last["data"]["error"]
    assert "traceback line 29" in last["data"]["error"]
    assert "traceback line 9\n" not in last["data"]["error"]
    assert status(client, run_id) == "failed"


@pytest.mark.usefixtures("slow")
def test_cancel_running(client: TestClient, runs_dir: Path) -> None:
    first, second = create(client, {"query": "q"}), create(client, {"query": "q"})
    wait_until(lambda: (runs_dir / first / "report.md").is_file())
    assert client.post(f"/api/runs/{first}/cancel").status_code == 202
    finished(client, first)
    assert events(runs_dir, first)[-1]["type"] == "run.cancelled"
    wait_until(lambda: status(client, second) != "queued")


def test_cancel_ignores_term_killed(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, {"query": "ignore-term"})
    wait_until(lambda: (runs_dir / run_id / "report.md").is_file())
    started = time.monotonic()
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 202
    finished(client, run_id)
    # The child ignores SIGTERM, so it is killed only after the app's grace (0.5 s).
    assert time.monotonic() - started >= 0.5
    assert events(runs_dir, run_id)[-1]["type"] == "run.cancelled"
    assert status(client, run_id) == "cancelled"


@pytest.mark.usefixtures("slow")
def test_cancel_queued(client: TestClient, runs_dir: Path) -> None:
    first, second = create(client, {"query": "q"}), create(client, {"query": "q"})
    response = client.post(f"/api/runs/{second}/cancel")
    assert response.status_code == 200
    assert not staging.staging_dir(runs_dir, second).exists()
    assert status(client, second) == "cancelled"
    finished(client, first)


@pytest.mark.usefixtures("slow")
def test_restart_requeues_in_order(make_app: MakeApp, runs_dir: Path) -> None:
    with TestClient(make_app(), base_url=BASE_URL) as client:
        running = create(client, {"query": "ignore-term"})
        queued = [create(client, {"query": "q"}), create(client, {"query": "q"})]
        wait_until(lambda: (runs_dir / running / "report.md").is_file())
    assert events(runs_dir, running)[-1]["type"] == "run.cancelled"
    with TestClient(make_app(), base_url=BASE_URL) as client:
        listed = [run["run_id"] for run in client.get("/api/runs").json()]
        assert running in listed
        assert status(client, queued[0]) == "running"
        assert (status(client, queued[1]), position(client, queued[1])) == ("queued", 1)
        for run_id in queued:
            finished(client, run_id)


@pytest.mark.usefixtures("slow")
def test_shutdown_cancels_running(make_app: MakeApp, runs_dir: Path) -> None:
    with TestClient(make_app(), base_url=BASE_URL) as client:
        run_id = create(client, {"query": "q"})
        wait_until(lambda: (runs_dir / run_id / "report.md").is_file())
    assert events(runs_dir, run_id)[-1]["type"] == "run.cancelled"


def test_huge_stderr_line_finishes(client: TestClient, runs_dir: Path) -> None:
    crash, after = create(client, {"query": "huge-stderr"}), create(client, {"query": "q"})
    finished(client, crash)
    last = events(runs_dir, crash)[-1]
    assert last["type"] == "run.failed"
    assert "process exited with code 1" in last["data"]["error"]
    assert "xxxx" in last["data"]["error"]
    finished(client, after)
    assert status(client, after) == "done"


def test_bad_line_does_not_stall(client: TestClient) -> None:
    bad, after = create(client, {"query": "bad-line"}), create(client, {"query": "q"})
    finished(client, bad)
    finished(client, after)
    assert (status(client, bad), status(client, after)) == ("done", "done")


def test_partial_line_then_kill(client: TestClient, runs_dir: Path) -> None:
    run_id, after = create(client, {"query": "partial-kill"}), create(client, {"query": "q"})
    log = runs_dir / run_id / "events.jsonl"
    wait_until(lambda: log.is_file() and not log.read_bytes().endswith(b"\n"))
    complete = log.read_bytes().rsplit(b"\n", 1)[0].count(b"\n") + 1
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 202
    finished(client, run_id)
    logged = RunStore(runs_dir, runs_dir).read_events(run_id)
    assert (logged[-1].type, logged[-1].seq) == ("run.cancelled", complete + 1)
    assert [event.seq for event in logged] == list(range(1, complete + 2))
    finished(client, after)
    assert status(client, after) == "done"


def test_finish_error_still_frees_slot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(RunStore, "append_event", broken)
    crash, after = create(client, {"query": "crash"}), create(client, {"query": "q"})
    wait_until(lambda: status(client, crash) != "running" and status(client, after) == "done")
    assert f"run {crash}: finishing the run failed" in caplog.text
    assert "disk full" in caplog.text


@pytest.mark.usefixtures("slow")
def test_lifecycle_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="wosarcher")
    first, second = create(client, {"query": "q"}), create(client, {"query": "q"})
    finished(client, first)
    finished(client, second)
    crash = create(client, {"query": "crash"})
    finished(client, crash)
    wait_until(lambda: f"run {crash} failed" in caplog.text)
    text = caplog.text
    assert f"run {second} queued (position 1)" in text
    assert f"run {first} started: run pid " in text
    assert f"run {first} done" in text
    assert f"run {crash}: traceback line 29" in text
    assert f"run {crash} failed in -: process exited with code 1" in text
    failed = [r for r in caplog.records if r.getMessage().startswith(f"run {crash} failed")]
    assert failed[0].levelno == logging.WARNING


@pytest.mark.usefixtures("slow")
def test_cancel_queued_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="wosarcher")
    first, second = create(client, {"query": "q"}), create(client, {"query": "q"})
    client.post(f"/api/runs/{second}/cancel")
    assert f"run {second} cancelled while queued" in caplog.text
    finished(client, first)


def test_ended_limit(client: TestClient) -> None:
    running = create(client, {"query": "ignore-term"})
    queued: list[str] = []
    for _ in range(ENDED_LIMIT + 1):
        run_id = create(client, {"query": "q"})
        assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
        queued.append(run_id)
    assert client.get(f"/api/runs/{queued[0]}").status_code == 404
    assert status(client, queued[1]) == "cancelled"
    assert status(client, queued[-1]) == "cancelled"
    client.post(f"/api/runs/{running}/cancel")
    finished(client, running)


def seen(client: TestClient, run_id: str) -> str | None:
    """The run's status; None while its directory does not exist yet."""
    return client.get(f"/api/runs/{run_id}").json().get("status")


def hold(runs_dir: Path, config_dir: Path, run_id: str = "cli-run") -> Held:
    held = RunStore(runs_dir, runs_dir, config_dir).slots.try_take(SlotEntry(run_id=run_id, origin="cli"))
    assert held is not None
    return held


@pytest.mark.usefixtures("slow")
def test_waits_behind_a_slot_held_elsewhere(client: TestClient, runs_dir: Path, config_dir: Path) -> None:
    held = hold(runs_dir, config_dir)
    run_id = create(client, {"query": "q"})
    time.sleep(0.6)
    assert (status(client, run_id), position(client, run_id)) == ("queued", 1)
    assert not (runs_dir / run_id).exists()
    held.close()
    wait_until(lambda: status(client, run_id) == "running", timeout=2)
    finished(client, run_id)


@pytest.mark.usefixtures("slow")
def test_raising_the_limit_starts_a_queued_run(client: TestClient) -> None:
    first, second = create(client, {"query": "q"}), create(client, {"query": "q"})
    assert status(client, second) == "queued"
    assert client.put("/api/settings", json={"max_concurrent_runs": 2}).status_code == 200
    wait_until(lambda: status(client, second) == "running", timeout=2)
    finished(client, first)
    finished(client, second)


@pytest.mark.usefixtures("slow")
def test_lowering_the_limit_keeps_running_runs(
    make_app: MakeApp, runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_STEP", "0.1")
    with TestClient(make_app(limit=2), base_url=BASE_URL) as client:
        runs = [create(client, {"query": "q"}) for _ in range(3)]
        assert client.put("/api/settings", json={"max_concurrent_runs": 1}).status_code == 200
        time.sleep(0.6)
        assert [status(client, run_id) for run_id in runs] == ["running", "running", "queued"]
        for run_id in runs:
            finished(client, run_id)
    ends = [events(runs_dir, run_id)[-1]["ts"] for run_id in runs[:2]]
    assert events(runs_dir, runs[2])[0]["ts"] >= max(ends)


def test_restart_queues_behind_a_cli_ticket(make_app: MakeApp, runs_dir: Path, config_dir: Path) -> None:
    held = hold(runs_dir, config_dir, "holder")
    with TestClient(make_app(), base_url=BASE_URL) as client:
        staged = create(client, {"query": "q"})
    cli = external("cli-run", steps=2)
    try:
        wait_until(lambda: RunStore(runs_dir, runs_dir, config_dir).slots.live("cli-run") == "queued")
        with TestClient(make_app(), base_url=BASE_URL) as client:
            assert (position(client, "cli-run"), position(client, staged)) == (1, 2)
            held.close()
            wait_until(lambda: seen(client, "cli-run") == "done")
            finished(client, staged)
            assert status(client, staged) == "done"
    finally:
        cli.kill()


def test_cancel_cli_run(client: TestClient, runs_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="wosarcher.server.manager")
    cli = external("cli-run", steps=200)
    wait_until(lambda: seen(client, "cli-run") == "running")
    response = client.post("/api/runs/cli-run/cancel")
    assert (response.status_code, response.json()) == (202, {"run_id": "cli-run", "result": "signalled"})
    assert cli.wait(timeout=5) == 130
    assert events(runs_dir, "cli-run")[-1]["type"] == "run.cancelled"
    assert status(client, "cli-run") == "cancelled"
    assert "cli-run" in caplog.text


def test_cancel_waiting_cli_run(client: TestClient, runs_dir: Path, config_dir: Path) -> None:
    held = hold(runs_dir, config_dir, "holder")
    cli = external("cli-run")
    wait_until(lambda: seen(client, "cli-run") == "queued")
    assert client.post("/api/runs/cli-run/cancel").status_code == 202
    assert cli.wait(timeout=5) == 130
    held.close()
    assert [event["type"] for event in events(runs_dir, "cli-run")] == ["run.cancelled"]


@pytest.mark.usefixtures("slow")
def test_slot_state(make_app: MakeApp, runs_dir: Path, config_dir: Path, password_hash: str) -> None:
    AuthStore(config_dir / "auth.json").set_password(password_hash)
    _, token = AuthStore(config_dir / "auth.json").add_token("ci-runner", datetime.now(UTC))
    held = hold(runs_dir, config_dir)
    with TestClient(make_app(limit=2), base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"}) as client:
        assert client.get("/api/slots").json() == {
            "limit": 2,
            "held": [{"run_id": "cli-run", "origin": "cli", "token_name": None, "started": ANY}],
            "queued": [],
        }
        first = create(client, {"query": "q"})
        api = create(client, {"query": "q"})
        state = client.get("/api/slots").json()
        assert [(h["run_id"], h["origin"]) for h in state["held"]] == [("cli-run", "cli"), (first, "api")]
        assert state["queued"] == [{"run_id": api, "origin": "api", "token_name": "ci-runner"}]
        assert client.get(f"/api/runs/{api}").json()["token_name"] == "ci-runner"
        held.close()
        finished(client, first)
        finished(client, api)
    args = argv(runs_dir, api)
    at = args.index("--origin")
    assert args[at : at + 4] == ["--origin", "api", "--token-name", "ci-runner"]
    assert args[-2] == "--slot-fd"


def test_cli_run_listed_as_running(client: TestClient, runs_dir: Path) -> None:
    cli = external("cli-run", steps=200)
    try:
        wait_until(lambda: seen(client, "cli-run") == "running")
        listed = next(run for run in client.get("/api/runs").json() if run["run_id"] == "cli-run")
        assert (listed["status"], listed["origin"]) == ("running", "cli")
    finally:
        cli.kill()
        cli.wait()
    assert status(client, "cli-run") == "interrupted"


def test_cli_run_cannot_be_deleted_or_forked(client: TestClient, runs_dir: Path) -> None:
    cli = external("cli-run", steps=200)
    try:
        wait_until(lambda: seen(client, "cli-run") == "running")
        assert client.delete("/api/runs/cli-run").status_code == 409
        assert client.post("/api/runs/cli-run/fork", json={"from": "write"}).status_code == 409
        assert (runs_dir / "cli-run").is_dir()
    finally:
        cli.kill()
        cli.wait()

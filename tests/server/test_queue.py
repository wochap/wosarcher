from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.server.conftest import BASE_URL, MakeApp, create, events, finished, status, wait_until
from wosarcher.server import staging


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
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 202
    finished(client, run_id)
    assert events(runs_dir, run_id)[-1]["type"] == "run.cancelled"
    assert status(client, run_id) == "cancelled"


@pytest.mark.usefixtures("slow")
def test_cancel_queued(client: TestClient, runs_dir: Path) -> None:
    first, second = create(client, {"query": "q"}), create(client, {"query": "q"})
    response = client.post(f"/api/runs/{second}/cancel")
    assert response.status_code == 200
    assert not staging.staging_dir(runs_dir, second).exists()
    assert client.get(f"/api/runs/{second}").status_code == 404
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

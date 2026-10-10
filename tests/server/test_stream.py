import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from tests.server.conftest import WS_URL, create, events, external, finished, wait_until
from tests.server.test_runs import on_disk
from wosarcher.models import SlotEntry
from wosarcher.store import RunStore

Message = dict[str, Any]


def read_to_close(socket: WebSocketTestSession) -> tuple[list[Message], int]:
    messages: list[Message] = []
    while True:
        try:
            messages.append(socket.receive_json())
        except WebSocketDisconnect as closed:
            return messages, closed.code


def logged(messages: list[Message]) -> list[int]:
    live = {"report.delta", "report.snapshot", "run.queued"}
    return [m["seq"] for m in messages if m["type"] not in live]


def rebuilt(messages: list[Message]) -> str:
    text = ""
    for message in messages:
        if message["type"] == "report.snapshot":
            text = message["data"]["text"]
        elif message["type"] == "report.delta":
            text += message["data"]["text"]
    return text


def test_unknown_run_4404(client: TestClient) -> None:
    with client.websocket_connect(f"{WS_URL}/api/runs/missing/events") as socket:
        assert read_to_close(socket) == ([], 4404)


def test_finished_run_replay_snapshot_close(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    (runs_dir / "r" / "report.md").write_text("# Report")
    with client.websocket_connect(f"{WS_URL}/api/runs/r/events?since=0") as socket:
        messages, code = read_to_close(socket)
    assert [m["type"] for m in messages] == ["run.started", "run.done", "report.snapshot"]
    assert set(messages[0]) == {"seq", "run_id", "ts", "type", "data"}
    assert (messages[2]["seq"], messages[2]["data"]["text"], code) == (2, "# Report", 1000)


def test_reconnect_since(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    with client.websocket_connect(f"{WS_URL}/api/runs/r/events?since=1") as socket:
        messages, code = read_to_close(socket)
    assert ([m["seq"] for m in messages], code) == ([2], 1000)


def test_live_run_no_gaps(client: TestClient, runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_STEP", "0.1")
    run_id = create(client, {"query": "slow"})
    first: list[Message] = []
    with client.websocket_connect(f"{WS_URL}/api/runs/{run_id}/events") as socket:
        while sum(m["type"] == "report.delta" for m in first) < 3:
            first.append(socket.receive_json())
    since = max(logged(first))
    with client.websocket_connect(f"{WS_URL}/api/runs/{run_id}/events?since={since}") as socket:
        second, code = read_to_close(socket)
    finished(client, run_id)
    assert code == 1000
    assert second[-1]["type"] == "run.done"
    seqs = logged(first) + logged(second)
    assert seqs == [event["seq"] for event in events(runs_dir, run_id)]
    assert rebuilt(second) == (runs_dir / run_id / "report.md").read_text()
    deltas = [m for m in second if m["type"] == "report.delta"]
    assert all(m["seq"] >= since for m in deltas)


def test_queued_position_updates(client: TestClient) -> None:
    runs = [create(client, {"query": "slow"}) for _ in range(3)]
    with client.websocket_connect(f"{WS_URL}/api/runs/{runs[2]}/events") as socket:
        first = socket.receive_json()
        assert (first["type"], first["data"]["position"], first["seq"]) == ("run.queued", 2, 0)
        second = socket.receive_json()
        assert (second["type"], second["data"]["position"]) == ("run.queued", 1)
    for run_id in runs:
        finished(client, run_id)


def test_cancel_queued_notifies(client: TestClient) -> None:
    running = create(client, {"query": "slow"})
    queued = create(client, {"query": "slow"})
    with client.websocket_connect(f"{WS_URL}/api/runs/{queued}/events") as socket:
        first = socket.receive_json()
        assert (first["type"], first["data"]["position"]) == ("run.queued", 1)
        assert client.post(f"/api/runs/{queued}/cancel").status_code == 200
        messages, code = read_to_close(socket)
    assert ([m["type"] for m in messages], code) == (["run.cancelled"], 1000)
    finished(client, running)


def test_ended_queued_run_socket(client: TestClient) -> None:
    running, queued = create(client, {"query": "slow"}), create(client, {"query": "slow"})
    assert client.post(f"/api/runs/{queued}/cancel").status_code == 200
    with client.websocket_connect(f"{WS_URL}/api/runs/{queued}/events") as socket:
        messages, code = read_to_close(socket)
    assert ([(m["type"], m["seq"]) for m in messages], code) == ([("run.cancelled", 0)], 1000)
    finished(client, running)


def test_early_exit_socket(client: TestClient) -> None:
    run_id = create(client, {"query": "early-exit"})
    finished(client, run_id)
    with client.websocket_connect(f"{WS_URL}/api/runs/{run_id}/events") as socket:
        messages, code = read_to_close(socket)
    assert ([(m["type"], m["seq"]) for m in messages], code) == ([("run.failed", 0)], 1000)
    assert "unknown profile 'x'" in messages[0]["data"]["error"]


def test_follow_cli_run(client: TestClient, runs_dir: Path) -> None:
    cli = external("cli-run", steps=20)
    wait_until(lambda: (runs_dir / "cli-run" / "events.jsonl").is_file())
    with client.websocket_connect(f"{WS_URL}/api/runs/cli-run/events?since=0") as socket:
        messages, code = read_to_close(socket)
    assert cli.wait(timeout=5) == 0
    assert (messages[-1]["type"], code) == ("run.done", 1000)
    assert logged(messages) == list(range(1, len(events(runs_dir, "cli-run")) + 1))
    assert any(m["type"] == "report.delta" for m in messages)
    assert rebuilt(messages) == (runs_dir / "cli-run" / "report.md").read_text()


def test_queued_cli_run(client: TestClient, runs_dir: Path, config_dir: Path) -> None:
    held = RunStore(runs_dir, runs_dir, config_dir).slots.try_take(SlotEntry(run_id="holder", origin="web"))
    assert held is not None
    cli = external("cli-run", steps=2)
    wait_until(lambda: client.get("/api/runs/cli-run").json().get("status") == "queued")
    with client.websocket_connect(f"{WS_URL}/api/runs/cli-run/events?since=0") as socket:
        queued = socket.receive_json()
        held.close()
        messages, code = read_to_close(socket)
    assert cli.wait(timeout=5) == 0
    assert queued["type"] == "run.queued"
    assert queued["data"]["position"] == 1
    assert queued["data"]["limit"] == 1
    assert [(h["run_id"], h["origin"]) for h in queued["data"]["held"]] == [("holder", "web")]
    assert (messages[-1]["type"], code) == ("run.done", 1000)


def test_killed_cli_run_closes(client: TestClient, runs_dir: Path) -> None:
    cli = external("cli-run", steps=500)
    wait_until(lambda: (runs_dir / "cli-run" / "report.md").is_file())
    with client.websocket_connect(f"{WS_URL}/api/runs/cli-run/events?since=0") as socket:
        socket.receive_json()
        cli.kill()
        killed = time.monotonic()
        _, code = read_to_close(socket)
    cli.wait()
    assert code == 1000
    assert time.monotonic() - killed < 2
    assert client.get("/api/runs/cli-run").json()["status"] == "interrupted"

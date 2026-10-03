from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from tests.server.conftest import create, events, finished
from tests.server.test_runs import on_disk

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
    with client.websocket_connect("/api/runs/missing/events") as socket:
        assert read_to_close(socket) == ([], 4404)


def test_finished_run_replay_snapshot_close(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    (runs_dir / "r" / "report.md").write_text("# Report")
    with client.websocket_connect("/api/runs/r/events?since=0") as socket:
        messages, code = read_to_close(socket)
    assert [m["type"] for m in messages] == ["run.started", "run.done", "report.snapshot"]
    assert set(messages[0]) == {"seq", "run_id", "ts", "type", "data"}
    assert (messages[2]["seq"], messages[2]["data"]["text"], code) == (2, "# Report", 1000)


def test_reconnect_since(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    with client.websocket_connect("/api/runs/r/events?since=1") as socket:
        messages, code = read_to_close(socket)
    assert ([m["seq"] for m in messages], code) == ([2], 1000)


def test_live_run_no_gaps(client: TestClient, runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_STEP", "0.1")
    run_id = create(client, {"query": "slow"})
    first: list[Message] = []
    with client.websocket_connect(f"/api/runs/{run_id}/events") as socket:
        while sum(m["type"] == "report.delta" for m in first) < 3:
            first.append(socket.receive_json())
    since = max(logged(first))
    with client.websocket_connect(f"/api/runs/{run_id}/events?since={since}") as socket:
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
    with client.websocket_connect(f"/api/runs/{runs[2]}/events") as socket:
        first = socket.receive_json()
        assert (first["type"], first["data"]["position"], first["seq"]) == ("run.queued", 2, 0)
        second = socket.receive_json()
        assert (second["type"], second["data"]["position"]) == ("run.queued", 1)
    for run_id in runs:
        finished(client, run_id)


def test_cancel_queued_notifies(client: TestClient) -> None:
    running = create(client, {"query": "slow"})
    queued = create(client, {"query": "slow"})
    with client.websocket_connect(f"/api/runs/{queued}/events") as socket:
        first = socket.receive_json()
        assert (first["type"], first["data"]["position"]) == ("run.queued", 1)
        assert client.post(f"/api/runs/{queued}/cancel").status_code == 200
        messages, code = read_to_close(socket)
    assert ([m["type"] for m in messages], code) == (["run.cancelled"], 1000)
    finished(client, running)

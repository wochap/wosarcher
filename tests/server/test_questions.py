"""Questions in a run: the open pause, answering it, presence on the event socket, and the request field."""

import json
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tests.conftest import Daemon, create_run
from tests.server.conftest import WS_URL, argv, create, finished, status, wait_until
from wosarcher.models import RunDetail

ANSWERS = [
    {"question_id": "q1", "option_ids": ["a"]},
    {"question_id": "q2", "option_ids": ["a", "b"], "other": "SUNAT"},
]


def waiting_run(client: TestClient) -> str:
    run_id = create(client, {"query": "ask"})
    wait_until(lambda: status(client, run_id) == "waiting")
    return run_id


def test_waiting_status_and_pending(client: TestClient) -> None:
    run_id = waiting_run(client)
    found = client.get(f"/api/runs/{run_id}").json()
    assert found["pending"]["kind"] == "clarify"
    assert found["pending"]["questions"] == 2
    listed = next(run for run in client.get("/api/runs").json() if run["run_id"] == run_id)
    assert listed["status"] == "waiting"
    assert listed["duration_s"] is None
    questions = client.get(f"/api/runs/{run_id}/questions")
    assert questions.status_code == 200
    assert questions.json()["pause_id"] == 1
    assert [q["id"] for q in questions.json()["questions"]] == ["q1", "q2"]
    client.post(f"/api/runs/{run_id}/continue", json={"pause_id": 1, "answers": ANSWERS})


def test_answer_a_pause(client: TestClient, runs_dir: Path) -> None:
    run_id = waiting_run(client)
    response = client.post(f"/api/runs/{run_id}/continue", json={"pause_id": 1, "answers": ANSWERS})
    assert response.status_code == 202
    wait_until(lambda: status(client, run_id) == "done")
    events = [json.loads(line) for line in (runs_dir / run_id / "events.jsonl").read_text().splitlines()]
    answered = next(event for event in events if event["type"] == "input.answered")
    assert answered["data"]["answered_by"] == "user"
    assert answered["data"]["answers"][1]["other"] == "SUNAT"
    assert client.get(f"/api/runs/{run_id}/questions").status_code == 404
    assert client.get(f"/api/runs/{run_id}/questions").json()["error"] == "not_waiting"


def test_not_waiting(client: TestClient) -> None:
    run_id = create(client, {"query": "slow"})
    response = client.post(f"/api/runs/{run_id}/continue", json={"pause_id": 1, "answers": ANSWERS})
    assert response.status_code == 409
    assert response.json()["error"] == "not_waiting"
    assert client.post("/api/runs/nope/continue", json={"pause_id": 1, "answers": ANSWERS}).status_code == 404


def test_missing_answer(client: TestClient) -> None:
    run_id = waiting_run(client)
    response = client.post(f"/api/runs/{run_id}/continue", json={"pause_id": 1, "answers": ANSWERS[:1]})
    assert response.status_code == 422
    assert "q2" in response.json()["detail"]
    assert status(client, run_id) == "waiting"
    wrong = client.post(f"/api/runs/{run_id}/continue", json={"pause_id": 2, "answers": ANSWERS})
    assert wrong.status_code == 409
    client.post(f"/api/runs/{run_id}/continue", json={"pause_id": 1, "answers": ANSWERS})


def test_agent_answers(daemon: Daemon) -> None:
    """A client on the Unix socket is an agent."""
    run_id = create_run(daemon, "ask")
    with httpx.Client(transport=httpx.HTTPTransport(uds=str(daemon.socket)), base_url="http://localhost") as http:
        wait_until(lambda: http.get(f"/api/runs/{run_id}").json()["status"] == "waiting")
        response = http.post(f"/api/runs/{run_id}/continue", json={"pause_id": 1, "answers": ANSWERS})
        assert response.status_code == 202
        wait_until(lambda: http.get(f"/api/runs/{run_id}").json()["status"] == "done")
    lines = (daemon.runs_dir / run_id / "events.jsonl").read_text().splitlines()
    answered = next(json.loads(line) for line in lines if '"input.answered"' in line)
    assert answered["data"]["answered_by"] == "agent"


def test_presence_touches_the_hold_file(client: TestClient, runs_dir: Path) -> None:
    run_id = waiting_run(client)
    hold = runs_dir / run_id / "input" / "1.hold"
    assert not hold.exists()
    with client.websocket_connect(f"{WS_URL}/api/runs/{run_id}/events?since=0") as socket:
        socket.send_text("not json")
        socket.send_text(json.dumps({"type": "hello"}))
        socket.send_text(json.dumps({"type": "presence"}))
        wait_until(hold.exists)
        before = hold.stat().st_mtime
        time.sleep(0.05)
        socket.send_text(json.dumps({"type": "presence"}))
        wait_until(lambda: hold.stat().st_mtime > before)
    client.post(f"/api/runs/{run_id}/continue", json={"pause_id": 1, "answers": ANSWERS})


def test_presence_on_a_running_run(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, {"query": "slow"})
    with client.websocket_connect(f"{WS_URL}/api/runs/{run_id}/events?since=0") as socket:
        socket.send_text(json.dumps({"type": "presence"}))
        first = json.loads(socket.receive_text())
    assert isinstance(first["type"], str)
    assert not (runs_dir / run_id / "input").exists()


def test_questions_request_field(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, {"query": "q", "questions": {"clarify": False, "rounds": False, "timeout": 120}})
    finished(client, run_id)
    args = argv(runs_dir, run_id)
    sets = [args[n + 1] for n, value in enumerate(args) if value == "--set"]
    assert "questions.clarify=false" in sets
    assert "questions.rounds=false" in sets
    assert "questions.timeout=120" in sets
    assert "questions.max_wait=1800" in sets
    detail = RunDetail.model_validate(client.get(f"/api/runs/{run_id}").json())
    assert detail.form is not None
    assert detail.form.questions.timeout == 120


def test_global_questions_apply(client: TestClient, runs_dir: Path) -> None:
    body = client.get("/api/settings").json()
    body["questions"]["timeout"] = 90
    client.put("/api/settings", json=body)
    run_id = create(client, {"query": "q"})
    finished(client, run_id)
    args = argv(runs_dir, run_id)
    assert "questions.timeout=90" in [args[n + 1] for n, value in enumerate(args) if value == "--set"]


def test_invalid_timeout(client: TestClient) -> None:
    response = client.post(
        "/api/runs", files={"request": (None, json.dumps({"query": "q", "questions": {"timeout": 4000}}))}
    )
    assert response.status_code == 422
    assert "questions.timeout" in response.json()["detail"]

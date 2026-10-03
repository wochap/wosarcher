import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.server.conftest import argv, create, finished, status, wait_until
from wosarcher.models import (
    RunCosts,
    RunDoneData,
    RunRecord,
    RunRequest,
    RunStartedData,
    UsageTotals,
    make_event,
)
from wosarcher.store import RunStore


def on_disk(
    runs_dir: Path, run_id: str, ends: bool, costs: float | None = None, request: RunRequest | None = None
) -> None:
    """A run directory as the CLI leaves it: started at 10:00:00, done at 10:02:05 when `ends`."""
    store = RunStore(runs_dir, runs_dir)
    store.run_dir(run_id).mkdir(parents=True)
    created = datetime(2026, 1, 1, 9, 59, tzinfo=UTC)
    record = RunRecord(
        run_id=run_id, created_at=created, request=request or RunRequest(query="q"), profile="p", settings={}
    )
    store.write_artifact(run_id, "request.json", record)
    started = RunStartedData(query="q", profile="p", parent_run_id=None, version=1, until=None)
    lines = [make_event(1, run_id, datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC), "run.started", None, started)]
    if ends:
        done = RunDoneData(until=None, totals=UsageTotals())
        lines.append(make_event(2, run_id, datetime(2026, 1, 1, 10, 2, 5, tzinfo=UTC), "run.done", None, done))
    (store.run_dir(run_id) / "events.jsonl").write_text("".join(e.model_dump_json() + "\n" for e in lines))
    if costs is not None:
        store.write_costs(run_id, RunCosts(stages={}, providers={}, total=UsageTotals(cost=costs)))


def summary(client: TestClient, run_id: str) -> dict[str, Any]:
    return client.get(f"/api/runs/{run_id}").json()


def test_create_with_attachment(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, {"query": "q", "sources": "both"}, [("notes.md", b"# notes")])
    finished(client, run_id)
    args = argv(runs_dir, run_id)
    attach = args[args.index("--attach") + 1]
    assert attach.endswith("/notes.md")
    assert args[args.index("--sources") + 1] == "both"
    assert (runs_dir / run_id / "attachments" / "notes.md").read_bytes() == b"# notes"


def test_missing_query_422(client: TestClient) -> None:
    response = client.post("/api/runs", files={"request": (None, '{"query": ""}')})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("query:")


def test_path_in_filename(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, {"query": "q"}, [("../../etc/notes.md", b"x")])
    finished(client, run_id)
    assert (runs_dir / run_id / "attachments" / "notes.md").read_bytes() == b"x"


def test_duplicate_attachments_422(client: TestClient) -> None:
    files = [("attachments", ("a/notes.md", b"1")), ("attachments", ("b/notes.md", b"2"))]
    response = client.post("/api/runs", files=[("request", (None, '{"query": "q"}')), *files])
    assert response.status_code == 422


def test_status_values(client: TestClient, runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    on_disk(runs_dir, "interrupted-run", ends=False)
    done = create(client, {"query": "ok"})
    finished(client, done)
    failed = create(client, {"query": "crash"})
    finished(client, failed)
    cancelled = create(client, {"query": "ignore-term"})
    wait_until(lambda: (runs_dir / cancelled / "report.md").is_file())
    queued = create(client, {"query": "slow"})
    assert status(client, cancelled) == "running"
    assert status(client, queued) == "queued"
    client.post(f"/api/runs/{cancelled}/cancel")
    finished(client, cancelled)
    finished(client, queued)
    listed = {run["run_id"]: run["status"] for run in client.get("/api/runs").json()}
    assert listed == {
        "interrupted-run": "interrupted",
        done: "done",
        failed: "failed",
        cancelled: "cancelled",
        queued: "done",
    }


def test_fork_lineage(client: TestClient) -> None:
    parent = create(client, {"query": "q"})
    finished(client, parent)
    child = client.post(f"/api/runs/{parent}/fork", json={"from": "write"}).json()["run_id"]
    finished(client, child)
    found = summary(client, child)
    assert (found["parent_run_id"], found["version"], found["fork_from"]) == (parent, 2, "write")


def test_summary_duration_and_cost(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True, costs=0.012)
    found = summary(client, "r")
    assert (found["status"], found["duration_s"], found["cost"]) == ("done", 125.0, 0.012)
    assert found["last_seq"] == 2
    assert found["costs"] is not None


def test_running_duration_null(client: TestClient) -> None:
    run_id = create(client, {"query": "slow"})
    found = summary(client, run_id)
    assert (found["status"], found["duration_s"]) == ("running", None)
    finished(client, run_id)


def test_delete_running_409(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, {"query": "slow"})
    wait_until(lambda: (runs_dir / run_id).is_dir())
    response = client.delete(f"/api/runs/{run_id}")
    assert (response.status_code, response.json()["error"]) == (409, "run_active")
    assert (runs_dir / run_id).is_dir()
    finished(client, run_id)


def test_delete_finished_204(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    assert client.delete("/api/runs/r").status_code == 204
    assert client.get("/api/runs").json() == []
    assert client.delete("/api/runs/r").status_code == 404


def test_delete_queued(client: TestClient) -> None:
    first, second = create(client, {"query": "slow"}), create(client, {"query": "slow"})
    assert client.delete(f"/api/runs/{second}").status_code == 204
    assert second not in [run["run_id"] for run in client.get("/api/runs").json()]
    finished(client, first)


def test_artifact_allowed(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    (runs_dir / "r" / "report.json").write_text('{"body": "b"}')
    (runs_dir / "r" / "report.md").write_text("# R")
    response = client.get("/api/runs/r/artifacts/report.json")
    assert (response.status_code, response.text) == (200, '{"body": "b"}')
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert client.get("/api/runs/r/artifacts/report.md").headers["content-type"] == "text/markdown; charset=utf-8"
    assert client.get("/api/runs/r/artifacts/events.jsonl").headers["content-type"].startswith("application/x-ndjson")


def test_artifact_not_listed_404(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    on_disk(runs_dir, "other", ends=True)
    (runs_dir / "other" / "report.md").write_text("secret")
    (runs_dir / "r" / "attachments").mkdir()
    for name in ("..%2Fother%2Freport.md", "attachments", "argv.json"):
        assert client.get(f"/api/runs/r/artifacts/{name}").status_code == 404


def test_artifact_missing_404(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    assert client.get("/api/runs/r/artifacts/context.json").status_code == 404


def test_cancel_finished_409(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    response = client.post("/api/runs/r/cancel")
    assert response.status_code == 409
    assert response.json() == {
        "error": "run_not_active",
        "detail": "run r is not queued or running (status done)",
        "run_id": "r",
        "status": "done",
    }
    assert client.post("/api/runs/missing/cancel").status_code == 404


def test_cancel_failed_409_status(client: TestClient) -> None:
    run_id = create(client, {"query": "crash"})
    finished(client, run_id)
    response = client.post(f"/api/runs/{run_id}/cancel")
    assert (response.status_code, response.json()["status"]) == (409, "failed")


def test_cancel_ended_queued_409(client: TestClient) -> None:
    first, second = create(client, {"query": "slow"}), create(client, {"query": "slow"})
    assert client.post(f"/api/runs/{second}/cancel").status_code == 200
    response = client.post(f"/api/runs/{second}/cancel")
    assert (response.status_code, response.json()["status"]) == (409, "cancelled")
    finished(client, first)


def test_cancelled_queued_run_still_shown(client: TestClient) -> None:
    first, second = create(client, {"query": "slow"}), create(client, {"query": "slow"})
    client.post(f"/api/runs/{second}/cancel")
    response = client.get(f"/api/runs/{second}")
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["last_seq"]) == ("cancelled", 0)
    assert second in [run["run_id"] for run in client.get("/api/runs").json()]
    assert client.delete(f"/api/runs/{second}").status_code == 204
    assert client.get(f"/api/runs/{second}").status_code == 404
    finished(client, first)


def test_early_exit_run_failed(client: TestClient) -> None:
    run_id = create(client, {"query": "early-exit"})
    finished(client, run_id)
    found = summary(client, run_id)
    assert found["status"] == "failed"
    assert "unknown profile 'x'" in found["error"]


def test_files_without_attachments_422(client: TestClient, runs_dir: Path) -> None:
    fields = [("request", (None, json.dumps({"query": "q", "sources": "files"}).encode()))]
    response = client.post("/api/runs", files=fields)
    assert (response.status_code, response.json()["error"]) == (422, "invalid_attachment")
    assert not list((runs_dir / ".queue").glob("*"))


def test_rerun_files_without_attachments_422(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True, request=RunRequest(query="q", sources="files"))
    response = client.post("/api/runs/r/rerun")
    assert (response.status_code, response.json()["error"]) == (422, "invalid_attachment")
    assert not list((runs_dir / ".queue").glob("*"))


def test_fork_write_with_tone(client: TestClient, runs_dir: Path) -> None:
    parent = create(client, {"query": "q"})
    finished(client, parent)
    response = client.post(f"/api/runs/{parent}/fork", json={"from": "write", "writing": {"tone": "critical"}})
    assert response.status_code == 201
    child = response.json()["run_id"]
    finished(client, child)
    args = argv(runs_dir, child)
    assert args[:3] == ["fork", parent, "--from"]
    assert args[3] == "write"
    assert args[args.index("--set") + 1] == 'write.tone="critical"'
    assert summary(client, child)["writing"]["tone"] == "critical"


def test_fork_active_409(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, {"query": "slow"})
    wait_until(lambda: (runs_dir / run_id / "request.json").is_file())
    assert client.post(f"/api/runs/{run_id}/fork", json={"from": "write"}).status_code == 409
    finished(client, run_id)


def test_fork_unknown_stage_422(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    response = client.post("/api/runs/r/fork", json={"from": "polish"})
    assert response.status_code == 422
    assert "'select'" in response.json()["detail"]


def test_rerun_copies_attachments(client: TestClient, runs_dir: Path) -> None:
    request = {"query": "q", "writing": {"tone": "critical"}, "set": ["score.top_k=5"]}
    original = create(client, request, [("notes.md", b"n")])
    finished(client, original)
    client.put("/api/settings", json={"writing": {"tone": "formal"}, "sources": "web"})
    response = client.post(f"/api/runs/{original}/rerun")
    assert response.status_code == 201
    rerun = response.json()["run_id"]
    finished(client, rerun)
    args = argv(runs_dir, rerun)
    assert "/.queue/" in args[args.index("--attach") + 1]
    flags = [args[n + 1] for n, flag in enumerate(args) if flag == "--set"]
    first = argv(runs_dir, original)
    assert flags == [first[n + 1] for n, flag in enumerate(first) if flag == "--set"]
    assert "score.top_k=5" in flags
    found = summary(client, rerun)
    assert (found["version"], found["parent_run_id"]) == (1, None)
    assert found["writing"]["tone"] == "critical"
    assert (runs_dir / rerun / "attachments" / "notes.md").read_bytes() == b"n"


def test_rerun_unknown_404(client: TestClient) -> None:
    assert client.post("/api/runs/missing/rerun").status_code == 404


def test_rerun_queued_409(client: TestClient) -> None:
    first, second = create(client, {"query": "slow"}), create(client, {"query": "slow"})
    assert client.post(f"/api/runs/{second}/rerun").status_code == 409
    finished(client, first)
    finished(client, second)

from fastapi.testclient import TestClient

from tests.server.conftest import create


def test_unknown_run_404(client: TestClient) -> None:
    response = client.get("/api/runs/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": "run_not_found", "detail": "no run does-not-exist"}


def test_validation_names_field(client: TestClient) -> None:
    response = client.post("/api/runs", files={"request": (None, '{"query": "q", "writing": {"words": 0}}')})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert "writing.words" in response.json()["detail"]


def test_body_validation_names_field(client: TestClient) -> None:
    run_id = create(client, {"query": "q"})
    response = client.post(f"/api/runs/{run_id}/fork", json={"from": "write", "writing": {"words": 0}})
    assert response.status_code == 422
    assert "writing.words" in response.json()["detail"]

from fastapi.testclient import TestClient


def test_app_starts(client: TestClient) -> None:
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert response.json() == []

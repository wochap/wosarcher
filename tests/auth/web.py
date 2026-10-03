"""Helpers for the guard, login, and token route tests."""

from fastapi.testclient import TestClient

from tests.conftest import PASSWORD


def login(client: TestClient, password: str = PASSWORD) -> None:
    response = client.post("/api/login", json={"password": password})
    assert response.status_code == 200, response.text


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

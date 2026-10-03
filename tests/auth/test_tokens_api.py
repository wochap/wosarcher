from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.auth.web import bearer, login
from tests.server.conftest import BASE_URL


@pytest.fixture
def browser(auth_app: FastAPI) -> Iterator[TestClient]:
    client = TestClient(auth_app, base_url=BASE_URL)
    with client:
        login(client)
        yield client


def test_create_returns_token_once(browser: TestClient) -> None:
    response = browser.post("/api/tokens", json={"name": "laptop"})
    assert response.status_code == 201
    created = response.json()
    assert created["token"].startswith("wosarcher_")
    assert created["name"] == "laptop"
    assert created["token"] not in browser.get("/api/tokens").text


def test_list_masked(browser: TestClient) -> None:
    token = browser.post("/api/tokens", json={"name": "laptop"}).json()["token"]
    [listed] = browser.get("/api/tokens").json()
    assert listed["masked"] == f"wosarcher_••••{token[-4:]}"
    assert set(listed) == {"id", "name", "masked", "created", "last_used"}


def test_delete_204_and_404(browser: TestClient) -> None:
    token_id = browser.post("/api/tokens", json={"name": "laptop"}).json()["id"]
    assert browser.delete(f"/api/tokens/{token_id}").status_code == 204
    assert browser.get("/api/tokens").json() == []
    response = browser.delete(f"/api/tokens/{token_id}")
    assert response.status_code == 404
    assert response.json()["error"] == "token_not_found"


def test_token_cannot_mint_403(browser: TestClient) -> None:
    token = browser.post("/api/tokens", json={"name": "script"}).json()["token"]
    browser.cookies.clear()
    response = browser.post("/api/tokens", json={"name": "more"}, headers=bearer(token))
    assert response.status_code == 403
    assert browser.get("/api/tokens", headers=bearer(token)).status_code == 403

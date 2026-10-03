import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.auth.web import bearer, login
from tests.conftest import PASSWORD
from tests.server.conftest import BASE_URL, MakeApp
from wosarcher.auth import AuthStore, hash_password


@pytest.fixture
def auth_client(auth_app: FastAPI) -> TestClient:
    return TestClient(auth_app, base_url=BASE_URL)


def test_right_password_sets_cookie(auth_client: TestClient) -> None:
    with auth_client:
        response = auth_client.post("/api/login", json={"password": PASSWORD})
        assert response.status_code == 200
        assert response.json()["method"] == "cookie"
        assert "wosarcher_session" in response.cookies
        assert auth_client.get("/api/runs").status_code == 200


def test_wrong_password_attempts_left(auth_client: TestClient) -> None:
    with auth_client:
        response = auth_client.post("/api/login", json={"password": "wrong-password"})
        assert response.status_code == 401
        assert response.json()["error"] == "wrong_password"
        assert response.json()["attempts_left"] == 4


def test_paused_right_password_429(auth_client: TestClient) -> None:
    with auth_client:
        codes = [auth_client.post("/api/login", json={"password": "nope-nope"}).status_code for _ in range(5)]
        assert codes == [401, 401, 401, 401, 429]
        response = auth_client.post("/api/login", json={"password": PASSWORD})
        assert response.status_code == 429
        assert response.json()["error"] == "rate_limited"
        assert response.json()["retry_after"] == int(response.headers["Retry-After"])
        assert 0 < response.json()["retry_after"] <= 30
        assert "wosarcher_session" not in response.cookies


def test_cookie_attributes_https(auth_app: FastAPI) -> None:
    with TestClient(auth_app, base_url="https://127.0.0.1:8765") as client:
        response = client.post("/api/login", json={"password": PASSWORD})
        cookie = response.headers["set-cookie"]
        assert cookie.startswith("wosarcher_session=")
        for attribute in ("HttpOnly", "SameSite=strict", "Secure", "Max-Age=2592000", "Path=/"):
            assert attribute in cookie


def test_auth_disabled_409(make_app: MakeApp) -> None:
    with TestClient(make_app(), base_url=BASE_URL) as client:
        response = client.post("/api/login", json={"password": PASSWORD})
        assert response.status_code == 409
        assert response.json()["error"] == "auth_disabled"


def test_failure_logged_without_password(auth_client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with auth_client, caplog.at_level(logging.WARNING):
        auth_client.post("/api/login", json={"password": "secret-guess"})
    assert "failed login from testclient" in caplog.text
    assert "secret-guess" not in caplog.text


def test_logout_clears_cookie(auth_client: TestClient) -> None:
    with auth_client:
        login(auth_client)
        assert auth_client.post("/api/logout").status_code == 204
        assert auth_client.get("/api/runs").status_code == 401


def test_session_cookie_since(auth_client: TestClient) -> None:
    with auth_client:
        since = auth_client.post("/api/login", json={"password": PASSWORD}).json()["since"]
        session = auth_client.get("/api/session").json()
        assert (session["method"], session["since"]) == ("cookie", since)
        assert session["expires"] > since


def test_session_token_name(auth_client: TestClient, config_dir: Path) -> None:
    with auth_client:
        login(auth_client)
        token = auth_client.post("/api/tokens", json={"name": "laptop"}).json()["token"]
        auth_client.cookies.clear()
        session = auth_client.get("/api/session", headers=bearer(token)).json()
        assert (session["method"], session["token_name"]) == ("token", "laptop")


def test_session_disabled_none(make_app: MakeApp) -> None:
    with TestClient(make_app(), base_url=BASE_URL) as client:
        assert client.get("/api/session").json()["method"] == "none"


def test_password_change_ends_session(auth_client: TestClient, config_dir: Path) -> None:
    with auth_client:
        login(auth_client)
        token = auth_client.post("/api/tokens", json={"name": "script"}).json()["token"]
        AuthStore(config_dir / "auth.json").set_password(hash_password("another-password"))
        assert auth_client.get("/api/runs").status_code == 401
        auth_client.cookies.clear()
        assert auth_client.get("/api/runs", headers=bearer(token)).status_code == 200

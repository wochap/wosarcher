from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from tests.auth.web import bearer, login
from tests.server.conftest import BASE_URL, WS_URL, MakeApp, create, finished
from tests.server.test_stream import read_to_close
from wosarcher.auth import AuthStore
from wosarcher.config import AuthConfig

EVIL = "https://evil.example"


@pytest.fixture
def client(make_app: MakeApp) -> TestClient:
    return TestClient(make_app(), base_url=BASE_URL)


@pytest.fixture
def auth_client(auth_app: FastAPI) -> TestClient:
    return TestClient(auth_app, base_url=BASE_URL)


# Host and Origin


def test_rebound_host_403(client: TestClient) -> None:
    response = client.get("/api/runs", headers={"Host": "attacker.example:8765"})
    assert response.status_code == 403
    assert response.json()["error"] == "bad_host"
    assert client.get("/api/runs", headers={"Host": "localhost:8765"}).status_code == 200
    assert client.get("/api/runs", headers={"Host": "[::1]:8765"}).status_code == 200


def test_cross_site_post_403(auth_client: TestClient) -> None:
    with auth_client:
        login(auth_client)
        response = auth_client.post("/api/runs", files={"request": (None, '{"query": "q"}')}, headers={"Origin": EVIL})
        assert response.status_code == 403
        assert response.json()["error"] == "bad_origin"
        assert auth_client.get("/api/runs").json() == []


def test_same_origin_passes(auth_client: TestClient) -> None:
    with auth_client:
        login(auth_client)
        response = auth_client.post("/api/runs/missing/cancel", headers={"Origin": BASE_URL})
        assert response.status_code == 404


def test_missing_origin_passes(client: TestClient) -> None:
    with client:
        assert client.post("/api/runs/missing/cancel").status_code == 404


def test_allowed_origins_setting(make_app: MakeApp) -> None:
    app = make_app(auth=AuthConfig(allowed_origins=["https://wosarcher.example"]))
    with TestClient(app, base_url=BASE_URL) as client:
        assert client.post("/api/runs/x/cancel", headers={"Origin": "https://wosarcher.example"}).status_code == 404
        assert client.post("/api/runs/x/cancel", headers={"Origin": EVIL}).status_code == 403


def test_cross_site_websocket_rejected(auth_client: TestClient) -> None:
    with auth_client:
        login(auth_client)
        run_id = create(auth_client, {"query": "q"})
        finished(auth_client, run_id)
        url = f"{WS_URL}/api/runs/{run_id}/events"
        with pytest.raises(WebSocketDisconnect) as closed, auth_client.websocket_connect(url, headers={"Origin": EVIL}):
            pass
        assert closed.value.code == 1008


# Content type


def test_form_put_settings_415(client: TestClient) -> None:
    with client:
        before = client.get("/api/settings").json()
        response = client.put("/api/settings", data={"sources": "web"})
        assert response.status_code == 415
        assert response.json()["error"] == "unsupported_media_type"
        assert client.get("/api/settings").json() == before


def test_json_runs_post_415(client: TestClient) -> None:
    with client:
        assert client.post("/api/runs", json={"query": "q"}).status_code == 415


def test_multipart_runs_post_passes(client: TestClient) -> None:
    with client:
        finished(client, create(client, {"query": "q"}))


def test_delete_without_body_passes(client: TestClient) -> None:
    with client:
        assert client.delete("/api/runs/missing").status_code == 404


# Authentication


def test_no_credentials_401(auth_client: TestClient) -> None:
    with auth_client:
        response = auth_client.get("/api/runs")
        assert response.status_code == 401
        assert response.json()["error"] == "unauthenticated"


def test_bearer_ok_updates_last_used(auth_client: TestClient, config_dir: Path) -> None:
    store = AuthStore(config_dir / "auth.json")
    _, token = store.add_token("script", datetime.now(UTC))
    with auth_client:
        assert auth_client.get("/api/runs", headers=bearer(token)).status_code == 200
    [stored] = store.tokens()
    assert stored.last_used is not None


def test_revoked_token_401(auth_client: TestClient, config_dir: Path) -> None:
    store = AuthStore(config_dir / "auth.json")
    stored, token = store.add_token("script", datetime.now(UTC))
    with auth_client:
        assert auth_client.get("/api/runs", headers=bearer(token)).status_code == 200
        store.revoke(stored.id)
        assert auth_client.get("/api/runs", headers=bearer(token)).status_code == 401


def test_static_login_page_public(make_app: MakeApp, config_dir: Path, password_hash: str, tmp_path: Path) -> None:
    build = tmp_path / "build"
    build.mkdir()
    (build / "index.html").write_text("<p>app</p>")
    AuthStore(config_dir / "auth.json").set_password(password_hash)
    with TestClient(make_app(static_dir=build), base_url=BASE_URL) as client:
        response = client.get("/login")
        assert response.status_code == 200
        assert response.text == "<p>app</p>"


def test_websocket_without_cookie_rejected(auth_client: TestClient) -> None:
    with auth_client:
        with pytest.raises(WebSocketDisconnect) as closed, auth_client.websocket_connect(f"{WS_URL}/api/runs/r/events"):
            pass
        assert closed.value.code == 1008


def test_websocket_with_cookie_streams(auth_client: TestClient) -> None:
    with auth_client:
        login(auth_client)
        run_id = create(auth_client, {"query": "q"})
        finished(auth_client, run_id)
        with auth_client.websocket_connect(
            f"{WS_URL}/api/runs/{run_id}/events", headers={"Origin": BASE_URL}
        ) as socket:
            messages, code = read_to_close(socket)
        assert code == 1000
        assert any(message["type"] == "run.done" for message in messages)


def test_password_set_while_running(client: TestClient, config_dir: Path, password_hash: str) -> None:
    with client:
        assert client.get("/api/runs").status_code == 200
        AuthStore(config_dir / "auth.json").set_password(password_hash)
        assert client.get("/api/runs").status_code == 401


def test_non_ascii_cookie_401(auth_client: TestClient) -> None:
    with auth_client:
        response = auth_client.get("/api/runs", headers=[(b"cookie", "wosarcher_session=é.1.2.sig".encode())])
        assert (response.status_code, response.json()["error"]) == (401, "unauthenticated")


@pytest.mark.parametrize(
    ("trusted", "code", "error"), [("*", 401, "unauthenticated"), ("127.0.0.1", 403, "bad_origin")]
)
def test_forwarded_proto_trusted(auth_app: FastAPI, trusted: str, code: int, error: str) -> None:
    # uvicorn and Starlette type the ASGI interface separately; the objects match at runtime.
    proxied: Any = ProxyHeadersMiddleware(cast(Any, auth_app), trusted_hosts=trusted)
    headers = {"X-Forwarded-Proto": "https", "Host": "wos.lan", "Origin": "https://wos.lan"}
    with TestClient(proxied, base_url=BASE_URL) as client:
        response = client.post("/api/runs/missing/cancel", headers=headers)
        assert (response.status_code, response.json()["error"]) == (code, error)

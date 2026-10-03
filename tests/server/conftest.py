import json
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wosarcher.auth import AuthStore
from wosarcher.config import AuthConfig, ServerConfig, Settings
from wosarcher.server import create_app

FAKE = Path(__file__).with_name("fake_wosarcher.py")
# A loopback Host, so the guard's DNS-rebinding check passes without a password.
BASE_URL = "http://127.0.0.1:8765"
# `websocket_connect` ignores the client's base URL, so socket tests pass absolute URLs.
WS_URL = "ws://127.0.0.1:8765"
COMMAND = [sys.executable, str(FAKE)]

MakeApp = Callable[..., FastAPI]


@pytest.fixture
def runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Children inherit the environment, so the fake writes here too."""
    path = tmp_path / "runs"
    monkeypatch.setenv("WOSARCHER_RUN__RUNS_DIR", str(path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("FAKE_MODE", "ok")
    monkeypatch.setenv("FAKE_STEP", "0.05")
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)
    return path


@pytest.fixture
def config_dir(tmp_path: Path, runs_dir: Path) -> Path:
    return tmp_path / "config" / "wosarcher"


@pytest.fixture
def make_app(runs_dir: Path, config_dir: Path, tmp_path: Path) -> MakeApp:
    def make(
        limit: int = 1, static_dir: Path | None = None, grace: float = 0.5, auth: AuthConfig | None = None
    ) -> FastAPI:
        server = ServerConfig(max_concurrent_runs=limit, static_dir=static_dir or tmp_path / "no-build")
        settings = Settings(server=server, auth=auth or AuthConfig())
        return create_app(settings, runs_dir, config_dir, COMMAND, grace=grace)

    return make


@pytest.fixture
def client(make_app: MakeApp) -> Iterator[TestClient]:
    with TestClient(make_app(), base_url=BASE_URL) as test_client:
        yield test_client


@pytest.fixture
def auth_app(make_app: MakeApp, config_dir: Path, password_hash: str) -> FastAPI:
    """An app with the admin password `hunter22` stored in the temporary config directory."""
    AuthStore(config_dir / "auth.json").set_password(password_hash)
    return make_app()


def wait_until(condition: Callable[[], object], timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.02)


def create(client: TestClient, request: dict[str, Any], files: Sequence[tuple[str, bytes]] = ()) -> str:
    # A `None` file name makes a plain form field, so the body is always multipart.
    fields = [("request", (None, json.dumps(request).encode()))]
    uploads = [("attachments", (name, data)) for name, data in files]
    response = client.post("/api/runs", files=[*fields, *uploads])
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


def status(client: TestClient, run_id: str) -> str:
    return client.get(f"/api/runs/{run_id}").json()["status"]


def finished(client: TestClient, run_id: str) -> None:
    wait_until(lambda: status(client, run_id) not in ("queued", "running"))


def events(runs_dir: Path, run_id: str) -> list[dict[str, Any]]:
    path = runs_dir / run_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []


def argv(runs_dir: Path, run_id: str) -> list[str]:
    return json.loads((runs_dir / run_id / "argv.json").read_text())

import asyncio
import json
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import uvicorn

from wosarcher.auth import hash_password
from wosarcher.config import AuthConfig, ServerConfig, Settings
from wosarcher.ports import Exporter
from wosarcher.server import create_app
from wosarcher.server.guard import socket_listener

PASSWORD = "hunter22"
FAKE_ENGINE = [sys.executable, str(Path(__file__).parent / "server" / "fake_wosarcher.py")]


@pytest.fixture(scope="session")
def password_hash() -> str:
    """One real scrypt hash per session, so tests check what production runs."""
    return hash_password(PASSWORD)


@pytest.fixture
def runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Children inherit the environment, so the fake engine writes here too."""
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


@dataclass
class Daemon:
    """The server app with the fake engine, on a Unix socket (`WOSARCHER_SOCKET` points at it) and on TCP."""

    socket: Path
    url: str
    runs_dir: Path
    config_dir: Path


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start(servers: list[uvicorn.Server]) -> threading.Thread:
    """Serve on one event loop in a thread, as `wosarcherd serve` does on its main loop."""

    async def serve() -> None:
        await asyncio.gather(*(server.serve() for server in servers))

    thread = threading.Thread(target=asyncio.run, args=(serve(),), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not all(server.started for server in servers):
        if time.monotonic() > deadline or not thread.is_alive():
            raise AssertionError("server did not start")
        time.sleep(0.01)
    return thread


StartDaemon = Callable[..., Daemon]


@pytest.fixture
def start_daemon(
    runs_dir: Path, config_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[StartDaemon]:
    servers: list[uvicorn.Server] = []
    threads: list[threading.Thread] = []
    monkeypatch.delenv("WOSARCHER_URL", raising=False)
    monkeypatch.delenv("WOSARCHER_TOKEN", raising=False)

    def make(auth: AuthConfig | None = None, grace: float = 0.5, exporter: Exporter | None = None) -> Daemon:
        settings = Settings(server=ServerConfig(static_dir=tmp_path / "no-build"), auth=auth or AuthConfig())
        app = create_app(settings, runs_dir, config_dir, FAKE_ENGINE, grace=grace, exporter=exporter)
        path = tmp_path / "wosarcher.sock"
        port = free_port()
        unix = uvicorn.Server(uvicorn.Config(socket_listener(app), uds=str(path), lifespan="off", log_level="error"))
        tcp = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        servers.extend((tcp, unix))
        threads.append(start([tcp, unix]))
        monkeypatch.setenv("WOSARCHER_SOCKET", str(path))
        return Daemon(socket=path, url=f"http://127.0.0.1:{port}", runs_dir=runs_dir, config_dir=config_dir)

    yield make
    for server in servers:
        server.should_exit = True
    for thread in threads:
        thread.join(timeout=15)


@pytest.fixture
def daemon(start_daemon: StartDaemon) -> Daemon:
    return start_daemon()


def create_run(daemon: Daemon, query: str = "q") -> str:
    """A run created over the daemon's socket."""
    with httpx.Client(transport=httpx.HTTPTransport(uds=str(daemon.socket)), base_url="http://localhost") as http:
        response = http.post("/api/runs", files=[("request", (None, json.dumps({"query": query}).encode()))])
    assert response.status_code == 201, response.text
    return response.json()["run_id"]

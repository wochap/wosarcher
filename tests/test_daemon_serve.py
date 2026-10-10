"""`wosarcherd serve`: listeners, bind checks, and the socket's mode and authentication."""

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from tests.conftest import free_port
from wosarcher.daemon import app
from wosarcher.daemon import serve as serve_module
from wosarcher.server.guard import socket_listener


@pytest.fixture
def calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[list[Any]]]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    for name in ("WOSARCHER_PROFILE", "XDG_RUNTIME_DIR", "LISTEN_FDS", "LISTEN_PID"):
        monkeypatch.delenv(name, raising=False)
    found: list[list[Any]] = []

    async def fake_run(servers: list[Any]) -> None:
        found.append(servers)

    monkeypatch.setattr(serve_module, "run_servers", fake_run)
    yield found
    for servers in found:
        for _, sockets in servers:
            listeners: list[socket.socket] = sockets or []
            for listener in listeners:
                listener.close()


def tcp_config(call: list[Any]) -> Any:
    return call[0][0].config


def test_defaults(calls: list[list[Any]], tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 0, result.output
    [call] = calls
    config = tcp_config(call)
    assert (config.host, config.port, config.proxy_headers) == ("127.0.0.1", 8765, True)
    assert (config.log_level, config.forwarded_allow_ips) == ("info", "127.0.0.1")
    state = config.app.state.server
    assert state.command == [sys.executable, "-m", "wosarcher.daemon"]
    assert state.runs_dir == tmp_path / "data" / "wosarcher" / "runs"
    assert state.config_dir == tmp_path / "config" / "wosarcher"
    assert len(call) == 1, "no socket without XDG_RUNTIME_DIR"


def test_port_option(calls: list[list[Any]]) -> None:
    assert CliRunner().invoke(app, ["serve", "--port", "9000"]).exit_code == 0
    assert (tcp_config(calls[0]).host, tcp_config(calls[0]).port) == ("127.0.0.1", 9000)


def test_lan_without_password_refused(calls: list[list[Any]]) -> None:
    result = CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 2
    assert "wosarcherd auth set-password" in result.output
    assert calls == []


def test_lan_with_password_starts(calls: list[list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_AUTH__PASSWORD_HASH", "scrypt$15$8$1$salt$key")
    assert CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"]).exit_code == 0
    assert tcp_config(calls[0]).host == "0.0.0.0"


def test_localhost_name_allowed(calls: list[list[Any]]) -> None:
    for host in ("localhost", "127.0.0.2", "::1"):
        assert CliRunner().invoke(app, ["serve", "--host", host]).exit_code == 0
    assert len(calls) == 3


def test_forwarded_allow_ips_setting(calls: list[list[Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_SERVER__FORWARDED_ALLOW_IPS", '["172.17.0.1", "10.0.0.0/8"]')
    assert CliRunner().invoke(app, ["serve"]).exit_code == 0
    assert tcp_config(calls[0]).forwarded_allow_ips == "172.17.0.1,10.0.0.0/8"


def test_socket_from_runtime_dir(calls: list[list[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert CliRunner().invoke(app, ["serve"]).exit_code == 0
    [(_, _), (unix, [listener])] = calls[0]
    assert listener.family == socket.AF_UNIX
    assert unix.config.lifespan == "off"
    assert not (tmp_path / "wosarcher.sock").exists(), "removed on exit"


def test_socket_mode_and_stale_file(calls: list[list[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "w.sock"
    stale = socket.socket(socket.AF_UNIX)
    stale.bind(str(path))
    stale.close()
    modes: list[int] = []
    original = serve_module.bind

    def bind(target: Path) -> socket.socket:
        listener = original(target)
        modes.append(target.stat().st_mode & 0o777)
        return listener

    monkeypatch.setattr(serve_module, "bind", bind)
    assert CliRunner().invoke(app, ["serve", "--socket", str(path)]).exit_code == 0
    assert modes == [0o660]


def test_no_socket(calls: list[list[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert CliRunner().invoke(app, ["serve", "--no-socket"]).exit_code == 0
    assert len(calls[0]) == 1


def test_inherited_descriptor(calls: list[list[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(tmp_path / "systemd.sock"))
    listener.listen()
    saved = os.dup(serve_module.LISTEN_FD) if fd_open(serve_module.LISTEN_FD) else None
    os.dup2(listener.fileno(), serve_module.LISTEN_FD)
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    try:
        assert CliRunner().invoke(app, ["serve"]).exit_code == 0
        [_, (_, [inherited])] = calls[0]
        assert inherited.getsockname() == str(tmp_path / "systemd.sock")
        assert not (tmp_path / "wosarcher.sock").exists()
        inherited.detach()
    finally:
        listener.close()
        if saved is not None:
            os.dup2(saved, serve_module.LISTEN_FD)
            os.close(saved)


def fd_open(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def test_socket_listener_marks_requests() -> None:
    seen: list[dict[str, Any]] = []

    async def inner(scope: Any, _receive: Any, _send: Any) -> None:
        seen.append(scope)

    asyncio.run(socket_listener(inner)({"type": "http", "state": {"x": 1}}, None, None))  # pyright: ignore[reportArgumentType]
    assert seen[0]["state"] == {"x": 1, "listener": "socket"}


def test_serve_socket_session(tmp_path: Path, password_hash: str) -> None:
    """A real `wosarcherd serve`: the socket answers `method = "socket"` with a password set, TCP answers 401."""
    path, port = tmp_path / "w.sock", free_port()
    env = {
        **os.environ,
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "WOSARCHER_AUTH__PASSWORD_HASH": password_hash,
    }
    env.pop("WOSARCHER_PROFILE", None)
    argv = [sys.executable, "-m", "wosarcher.daemon", "serve", "--socket", str(path), "--port", str(port)]
    process = subprocess.Popen(argv, env=env, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert path.stat().st_mode & 0o777 == 0o660
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(path), retries=5), base_url="http://x") as http:
            assert http.get("/api/session").json()["method"] == "socket"
            assert http.get("/api/runs").status_code == 200
        assert httpx.get(f"http://127.0.0.1:{port}/api/runs").status_code == 401
    finally:
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=20) == 0
    assert not path.exists()

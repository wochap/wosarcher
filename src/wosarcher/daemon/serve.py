"""`wosarcherd serve`: the HTTP API, the event socket, and the frontend build, on TCP and a Unix socket.

Both listeners are `uvicorn.Server` instances on one event loop over the same
app; the TCP one runs the lifespan (the run manager). The Unix socket is the
descriptor systemd passed (`LISTEN_FDS`), else a socket bound here with mode
0660 at `--socket` or `server.socket`. Requests on it are marked for the guard
(`socket_listener`), which authenticates them with method `socket`.
"""

import asyncio
import contextlib
import ipaddress
import logging
import os
import signal
import socket
import sys
from collections.abc import Generator, Mapping, MutableMapping
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from wosarcher.auth import AuthStore
from wosarcher.cli.options import fail
from wosarcher.config import ConfigError, Settings, config_dir, resolve
from wosarcher.server import create_app
from wosarcher.server.guard import socket_listener
from wosarcher.store import RunStore

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
SOCKET_NAME = "wosarcher.sock"
SOCKET_MODE = 0o660
LISTEN_FD = 3
"""The first descriptor systemd passes (`SD_LISTEN_FDS_START`)."""

log = logging.getLogger(__name__)


class Server(uvicorn.Server):
    """A server that leaves signals to `serve`, which stops every listener at once."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield


def inherited(env: MutableMapping[str, str]) -> socket.socket | None:
    """The listening socket systemd passed to this process, if any; the variables are removed for run processes."""
    pid, count = env.pop("LISTEN_PID", None), env.pop("LISTEN_FDS", None)
    env.pop("LISTEN_FDNAMES", None)
    if pid not in (None, str(os.getpid())) or int(count or 0) < 1:
        return None
    return socket.socket(fileno=LISTEN_FD)


def socket_path(given: Path | None, settings: Settings, env: Mapping[str, str]) -> Path | None:
    if given is not None or settings.server.socket is not None:
        return given or settings.server.socket
    runtime = env.get("XDG_RUNTIME_DIR")
    return Path(runtime) / SOCKET_NAME if runtime else None


def bind(path: Path) -> socket.socket:
    """Bind a Unix socket at `path` with mode 0660, replacing a stale socket file nobody listens on."""
    if path.is_socket():
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.connect(str(path))
            except OSError:
                path.unlink()
            else:
                raise fail(f"{path} is in use by another server", 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    os.chmod(path, SOCKET_MODE)
    listener.listen(128)
    return listener


def listen_socket(given: Path | None, no_socket: bool, settings: Settings) -> tuple[socket.socket, Path | None] | None:
    """The Unix listener, with its path when this process bound it."""
    if no_socket:
        return None
    found = inherited(os.environ)
    if found is not None:
        return found, None
    path = socket_path(given, settings, os.environ)
    if path is None:
        return None
    try:
        return bind(path), path
    except OSError as error:
        raise fail(f"cannot listen on {path}: {error}", 2) from None


async def run_servers(servers: list[tuple[Server, list[socket.socket] | None]]) -> None:
    loop = asyncio.get_running_loop()

    def stop() -> None:
        for server, _ in servers:
            server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop)
    try:
        await asyncio.gather(*(server.serve(sockets) for server, sockets in servers))
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


def serve(
    host: Annotated[str | None, typer.Option("--host", help="Address to bind (default server.host).")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Port to bind (default server.port).")] = None,
    socket_: Annotated[
        Path | None, typer.Option("--socket", help="Unix socket to listen on (default server.socket).")
    ] = None,
    no_socket: Annotated[bool, typer.Option("--no-socket", help="Listen on TCP only.")] = False,
) -> None:
    """Serve the API under /api and the frontend build; each run is a `wosarcherd run` subprocess."""
    env = os.environ
    try:
        settings = resolve(None, [], env)
    except ConfigError as error:
        raise fail(error, 2) from None
    bind_host = host or settings.server.host
    if not is_loopback(bind_host) and not AuthStore.from_settings(settings, config_dir(env)).enabled():
        message = f"refusing to listen on {bind_host} without a password; run `wosarcherd auth set-password` first"
        raise fail(message, 2)
    store = RunStore.from_settings(settings, env)
    app = create_app(settings, store.runs_dir, config_dir(env), [sys.executable, "-m", "wosarcher.daemon"])
    level = settings.server.log_level
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, stream=sys.stderr)
    tcp = uvicorn.Config(
        app,
        host=bind_host,
        port=port or settings.server.port,
        proxy_headers=True,
        forwarded_allow_ips=",".join(settings.server.forwarded_allow_ips),
        log_level=level,
    )
    servers: list[tuple[Server, list[socket.socket] | None]] = [(Server(tcp), None)]
    listener = listen_socket(socket_, no_socket, settings)
    if listener is not None:
        unix = uvicorn.Config(socket_listener(app), lifespan="off", proxy_headers=False, log_level=level)
        servers.append((Server(unix), [listener[0]]))
        log.info("listening on unix socket %s", listener[1] or f"descriptor {LISTEN_FD}")
    try:
        asyncio.run(run_servers(servers))
    finally:
        if listener is not None and listener[1] is not None:
            listener[1].unlink(missing_ok=True)


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False

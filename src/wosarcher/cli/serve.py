"""`wosarcher serve`: the HTTP API, the event socket, and the frontend build."""

import ipaddress
import logging
import os
import sys
from typing import Annotated

import typer
import uvicorn

from wosarcher.auth import AuthStore
from wosarcher.cli import fail
from wosarcher.config import ConfigError, config_dir, resolve
from wosarcher.server import create_app
from wosarcher.store import RunStore

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def serve(
    host: Annotated[str | None, typer.Option("--host", help="Address to bind (default server.host).")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Port to bind (default server.port).")] = None,
) -> None:
    """Serve the API under /api and the frontend build; each run is a `wosarcher run` subprocess."""
    env = os.environ
    try:
        settings = resolve(None, [], env)
    except ConfigError as error:
        raise fail(error, 2) from None
    bind = host or settings.server.host
    if not is_loopback(bind) and not AuthStore.from_settings(settings, config_dir(env)).enabled():
        message = f"refusing to listen on {bind} without a password; run `wosarcher auth set-password` first"
        raise fail(ValueError(message), 2)
    store = RunStore.from_settings(settings, env)
    app = create_app(settings, store.runs_dir, config_dir(env), [sys.executable, "-m", "wosarcher"])
    level = settings.server.log_level
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT, stream=sys.stderr)
    uvicorn.run(
        app,
        host=bind,
        port=port or settings.server.port,
        proxy_headers=True,
        forwarded_allow_ips=",".join(settings.server.forwarded_allow_ips),
        log_level=level,
    )


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False

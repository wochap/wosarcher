"""`wosarcher serve`: the HTTP API, the event socket, and the frontend build."""

import os
import sys
from typing import Annotated

import typer
import uvicorn

from wosarcher.cli import fail
from wosarcher.config import ConfigError, config_dir, resolve
from wosarcher.server import create_app
from wosarcher.store import RunStore


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
    store = RunStore.from_settings(settings, env)
    app = create_app(settings, store.runs_dir, config_dir(env), [sys.executable, "-m", "wosarcher"])
    uvicorn.run(app, host=host or settings.server.host, port=port or settings.server.port, proxy_headers=True)

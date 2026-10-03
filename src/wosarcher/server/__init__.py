"""The HTTP server: JSON routes and the event socket under `/api`, plus the frontend build at `/`.

The guard (`guard.py`) checks every `/api` request: Host, Origin, content type, and login.

Every run is a subprocess of `command` (`[python, -m, wosarcher]` in production).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from wosarcher.auth import AuthStore
from wosarcher.config import Settings
from wosarcher.server import errors, login, meta, routes, stream, tokens
from wosarcher.server.guard import Guard
from wosarcher.server.limiter import LoginLimiter
from wosarcher.server.manager import GRACE_SECONDS, RunManager
from wosarcher.server.state import ServerState
from wosarcher.store import RunStore


def create_app(
    settings: Settings, runs_dir: Path, config_dir: Path, command: list[str], grace: float = GRACE_SECONDS
) -> FastAPI:
    # The server never uses the caches; the store only reads and appends run logs.
    store = RunStore(runs_dir, runs_dir)
    manager = RunManager(runs_dir, command, settings.server.max_concurrent_runs, store, grace)
    auth = AuthStore.from_settings(settings, config_dir)
    state = ServerState(settings, runs_dir, config_dir, command, store, manager, auth, LoginLimiter())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        await manager.start()
        yield
        await manager.shutdown()

    app = FastAPI(
        title="wosarcher", lifespan=lifespan, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json"
    )
    app.state.server = state
    app.include_router(routes.router)
    app.include_router(meta.router)
    app.include_router(stream.router)
    app.include_router(login.router)
    app.include_router(tokens.router)
    app.add_middleware(Guard, store=auth, config=settings.auth)
    static = settings.server.static_dir
    index = static / "index.html" if static.is_dir() else None
    errors.install(app, index)
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
    return app

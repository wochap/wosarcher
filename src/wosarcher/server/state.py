"""What every route needs, kept on `app.state.server` (no globals)."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from starlette.requests import HTTPConnection

from wosarcher.auth import AuthStore
from wosarcher.config import Settings
from wosarcher.ports import Exporter
from wosarcher.server.health import HealthCache
from wosarcher.server.limiter import LoginLimiter
from wosarcher.server.manager import RunManager
from wosarcher.store import RunStore


@dataclass
class ServerState:
    settings: Settings
    runs_dir: Path
    config_dir: Path
    command: list[str]
    store: RunStore
    manager: RunManager
    auth: AuthStore
    limiter: LoginLimiter
    health: HealthCache
    exporter: Exporter
    # Report exports converting at once; each runs pandoc and maybe Typst.
    exports: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2))


def get_state(connection: HTTPConnection) -> ServerState:
    """FastAPI dependency for routes and sockets."""
    return connection.app.state.server

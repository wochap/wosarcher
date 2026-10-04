"""What every route needs, kept on `app.state.server` (no globals)."""

from dataclasses import dataclass
from pathlib import Path

from starlette.requests import HTTPConnection

from wosarcher.auth import AuthStore
from wosarcher.config import Settings
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


def get_state(connection: HTTPConnection) -> ServerState:
    """FastAPI dependency for routes and sockets."""
    return connection.app.state.server

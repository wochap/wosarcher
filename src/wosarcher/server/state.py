"""What every route needs, kept on `app.state.server` (no globals)."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from starlette.requests import HTTPConnection

from wosarcher.auth import AuthStore
from wosarcher.config import Settings
from wosarcher.http import UsageLedger
from wosarcher.ports import LLM, Exporter
from wosarcher.server.health import HealthCache
from wosarcher.server.limiter import LoginLimiter
from wosarcher.server.manager import RunManager
from wosarcher.store import RunStore

DraftLLM = Callable[[Settings, httpx.AsyncClient, UsageLedger], LLM]


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
    draft_llm: "DraftLLM"
    """Builds the catalog draft call from the resolved settings (a fake in tests)."""
    # Report exports converting at once; each runs pandoc and maybe Typst.
    exports: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2))


def get_state(connection: HTTPConnection) -> ServerState:
    """FastAPI dependency for routes and sockets."""
    return connection.app.state.server

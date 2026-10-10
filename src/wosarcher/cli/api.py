"""The client's connection to `wosarcherd`: httpx for routes, `websockets` for run events.

`WOSARCHER_URL` (with `WOSARCHER_TOKEN` as a bearer token) wins; otherwise the
Unix socket at `WOSARCHER_SOCKET`, `$XDG_RUNTIME_DIR/wosarcher.sock`, or
`/run/wosarcher/api.sock`. A connection failure exits 69 and a 401 exits 2.
"""

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import typer
from websockets.asyncio.client import ClientConnection, connect, unix_connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from wosarcher.cli.options import fail
from wosarcher.config import CLIENT_ENV
from wosarcher.models import Event, parse_event

URL_VAR, TOKEN_VAR, SOCKET_VAR = CLIENT_ENV
SYSTEM_SOCKET = Path("/run/wosarcher/api.sock")
SOCKET_BASE = "http://localhost"
UNREACHABLE = 69
"""`EX_UNAVAILABLE`."""
CLOSE_UNKNOWN = 4404
TIMEOUT = httpx.Timeout(30.0, read=300.0)


@dataclass(frozen=True)
class Connection:
    url: str | None = None
    token: str | None = None
    socket: Path | None = None

    @property
    def label(self) -> str:
        return self.url or str(self.socket)

    @property
    def base(self) -> str:
        return (self.url or SOCKET_BASE).rstrip("/")

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.url and self.token else {}


def connection(env: Mapping[str, str]) -> Connection:
    if env.get(URL_VAR):
        return Connection(url=env[URL_VAR], token=env.get(TOKEN_VAR) or None)
    if env.get(SOCKET_VAR):
        return Connection(socket=Path(env[SOCKET_VAR]))
    runtime = env.get("XDG_RUNTIME_DIR")
    return Connection(socket=Path(runtime) / "wosarcher.sock" if runtime else SYSTEM_SOCKET)


def unreachable(conn: Connection) -> typer.Exit:
    where = f"URL {conn.url}" if conn.url else f"socket {conn.socket}"
    return fail(f"cannot reach the daemon at {where}; is `wosarcherd serve` running and may you use it?", UNREACHABLE)


def detail(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    if isinstance(body, dict) and "detail" in body:
        found: Any = body["detail"]  # pyright: ignore[reportUnknownVariableType]
        return found if isinstance(found, str) else json.dumps(found)
    return json.dumps(body)


class Api:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        transport = httpx.HTTPTransport(uds=str(conn.socket)) if conn.url is None else None
        self.http = httpx.Client(base_url=conn.base, headers=conn.headers(), transport=transport, timeout=TIMEOUT)

    def request(self, method: str, path: str, **options: Any) -> httpx.Response:
        """Send one request; exit 69 when the daemon cannot be reached and 2 on 401."""
        try:
            response = self.http.request(method, path, **options)
        except (httpx.ConnectError, httpx.ConnectTimeout, FileNotFoundError, PermissionError):
            raise unreachable(self.conn) from None
        if response.status_code == 401:
            raise fail(f"the daemon refused the request: {TOKEN_VAR} is missing or revoked", 2)
        return response

    def ok(self, method: str, path: str, **options: Any) -> httpx.Response:
        """A 2xx answer; any other exits 2 for a 4xx and 1 otherwise, printing the server's detail."""
        response = self.request(method, path, **options)
        if response.is_success:
            return response
        raise fail(detail(response), 2 if response.status_code < 500 else 1)

    def get(self, path: str, **options: Any) -> Any:
        return self.ok("GET", path, **options).json()

    async def socket(self, path: str) -> ClientConnection:
        if self.conn.url is None:
            return await unix_connect(str(self.conn.socket), f"ws://localhost{path}", open_timeout=30)
        uri = "ws" + self.conn.base.removeprefix("http") + path
        return await connect(uri, additional_headers=self.conn.headers(), open_timeout=30)

    async def events(self, run_id: str, since: int = 0) -> AsyncIterator[Event]:
        """The run's events from `since` until the server closes the socket; exit 2 for an unknown run."""
        try:
            socket = await self.socket(f"/api/runs/{run_id}/events?since={since}")
        except InvalidStatus as error:
            raise fail(f"the daemon refused the event socket (HTTP {error.response.status_code})", 2) from None
        except (OSError, InvalidHandshake, TimeoutError):
            raise unreachable(self.conn) from None
        async with socket:
            try:
                async for message in socket:
                    try:
                        yield parse_event(message if isinstance(message, str) else message.decode())
                    except ValueError:
                        continue
            except ConnectionClosed:
                pass
        if socket.close_code == CLOSE_UNKNOWN:
            raise fail(f"no run {run_id}", 2)


def api(env: Mapping[str, str]) -> Api:
    return Api(connection(env))

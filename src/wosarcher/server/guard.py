"""The request guard for `/api`: Host, Origin, content type, then authentication.

A pure ASGI middleware, so it sees WebSocket handshakes too. Paths outside
`/api` (the frontend build) pass untouched. The result is kept in
`scope["state"]["auth"]` for `GET /api/session`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from wosarcher.auth import AuthStore, Session, StoredToken, verify_session
from wosarcher.config import AuthConfig
from wosarcher.server.errors import body, is_api

COOKIE = "wosarcher_session"
STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
SCHEMES = {"ws": "http", "wss": "https"}
CLOSE_POLICY = 1008


@dataclass(frozen=True)
class Auth:
    method: Literal["cookie", "token", "none"]
    session: Session | None = None
    token: StoredToken | None = None


class RefusalError(Exception):
    def __init__(self, status: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.error = error
        self.detail = detail


class Guard:
    def __init__(self, app: ASGIApp, store: AuthStore, config: AuthConfig) -> None:
        self.app = app
        self.store = store
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not is_api(scope["path"]):
            await self.app(scope, receive, send)
            return
        connection = HTTPConnection(scope)
        try:
            scope.setdefault("state", {})["auth"] = self.check(connection, scope)
        except RefusalError as refusal:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": CLOSE_POLICY, "reason": refusal.detail})
            else:
                await body(refusal.status, refusal.error, refusal.detail)(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def check(self, connection: HTTPConnection, scope: Scope) -> Auth:
        method = "WEBSOCKET" if scope["type"] == "websocket" else scope["method"]
        path = scope["path"]
        enabled = self.store.enabled()
        host = connection.headers.get("host", "")
        if not enabled and host_name(host) not in LOOPBACK_HOSTS:
            raise RefusalError(403, "bad_host", f"host {host!r} is not a loopback name; set a password to allow it")
        origin = connection.headers.get("origin")
        if method in STATE_CHANGING | {"WEBSOCKET"} and origin is not None:
            own = f"{SCHEMES.get(scope['scheme'], scope['scheme'])}://{host}"
            if origin != own and origin not in self.config.allowed_origins:
                raise RefusalError(403, "bad_origin", f"origin {origin} may not send this request")
        if method in STATE_CHANGING and has_body(connection):
            check_content_type(connection, method, path)
        if method == "POST" and path == "/api/login":
            return Auth("none")
        auth = self.authenticate(connection) if enabled else Auth("none")
        if auth.method == "token" and (path == "/api/tokens" or path.startswith("/api/tokens/")):
            raise RefusalError(403, "forbidden", "token routes need a browser session")
        return auth

    def authenticate(self, connection: HTTPConnection) -> Auth:
        now = datetime.now(UTC)
        scheme, _, presented = connection.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and presented:
            token = self.store.find(presented.strip())
            if token is not None:
                self.store.touch(token, now)
                return Auth("token", token=token)
        cookie = connection.cookies.get(COOKIE)
        password_hash = self.store.password_hash()
        if cookie and password_hash:
            session = verify_session(cookie, self.store.secret(), password_hash, now)
            if session is not None:
                return Auth("cookie", session=session)
        raise RefusalError(401, "unauthenticated", "log in or send an API token")


def host_name(host: str) -> str:
    """`127.0.0.1:8765` -> `127.0.0.1`; `[::1]:8765` -> `[::1]`."""
    if host.startswith("["):
        return host.partition("]")[0] + "]"
    return host.partition(":")[0].lower()


def has_body(connection: HTTPConnection) -> bool:
    length = connection.headers.get("content-length", "0")
    chunked = "chunked" in connection.headers.get("transfer-encoding", "").lower()
    return chunked or (length.isdigit() and int(length) > 0)


def check_content_type(connection: HTTPConnection, method: str, path: str) -> None:
    media = connection.headers.get("content-type", "").partition(";")[0].strip().lower()
    expected = "multipart/form-data" if method == "POST" and path == "/api/runs" else "application/json"
    if media != expected:
        raise RefusalError(415, "unsupported_media_type", f"{method} {path} needs Content-Type {expected}")

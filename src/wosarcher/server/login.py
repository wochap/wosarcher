"""`POST /api/login`, `POST /api/logout`, and `GET /api/session`."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from wosarcher.auth import sign_session, verify_password, verify_session
from wosarcher.models import LoginError, LoginRequest, SessionInfo
from wosarcher.server.errors import RouteError
from wosarcher.server.guard import COOKIE, Auth
from wosarcher.server.state import ServerState, get_state

router = APIRouter(prefix="/api")
State = Annotated[ServerState, Depends(get_state)]
log = logging.getLogger(__name__)


def refused(status: int, error: LoginError, retry_after: int | None = None) -> JSONResponse:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return JSONResponse(error.model_dump(), status_code=status, headers=headers)


def paused(retry_after: int) -> JSONResponse:
    error = LoginError(error="rate_limited", detail="too many failed logins", retry_after=retry_after)
    return refused(429, error, retry_after)


@router.post("/login", response_model=SessionInfo)
async def login(payload: LoginRequest, request: Request, state: State) -> Response:
    password_hash = state.auth.password_hash()
    if password_hash is None:
        raise RouteError(409, "auth_disabled", "no password is set; run `wosarcher auth set-password`")
    ip = request.client.host if request.client else "unknown"
    retry_after = state.limiter.check(ip)
    if retry_after is not None:
        return paused(retry_after)
    if not await asyncio.to_thread(verify_password, payload.password, password_hash):
        left = state.limiter.fail(ip)
        log.warning("failed login from %s", ip)
        retry_after = state.limiter.check(ip)
        if retry_after is not None:
            return paused(retry_after)
        return refused(401, LoginError(error="wrong_password", detail="wrong password", attempts_left=left))
    state.limiter.succeed(ip)
    now = datetime.now(UTC)
    days = state.settings.auth.session_days
    value = sign_session(state.auth.secret(), password_hash, now, days)
    session = verify_session(value, state.auth.secret(), password_hash, now)
    assert session is not None
    info = SessionInfo(method="cookie", since=session.issued, expires=session.expires)
    response = JSONResponse(info.model_dump(mode="json"))
    secure = request.url.scheme == "https"
    response.set_cookie(COOKIE, value, max_age=days * 86400, path="/", httponly=True, samesite="strict", secure=secure)
    return response


@router.post("/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
    return response


@router.get("/session")
async def session(request: Request) -> SessionInfo:
    auth: Auth = request.state.auth
    if auth.session is not None:
        return SessionInfo(method="cookie", since=auth.session.issued, expires=auth.session.expires)
    if auth.token is not None:
        return SessionInfo(method="token", token_name=auth.token.name)
    return SessionInfo(method="none")

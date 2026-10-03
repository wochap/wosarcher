"""`GET/POST/DELETE /api/tokens`: API tokens for scripts; the guard limits these routes to browser sessions."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from wosarcher.auth import masked
from wosarcher.models import TokenCreate, TokenCreated, TokenInfo
from wosarcher.server.errors import RouteError
from wosarcher.server.state import ServerState, get_state

router = APIRouter(prefix="/api/tokens")
State = Annotated[ServerState, Depends(get_state)]


@router.get("")
async def list_tokens(state: State) -> list[TokenInfo]:
    return [
        TokenInfo(id=t.id, name=t.name, masked=masked(t.last4), created=t.created, last_used=t.last_used)
        for t in state.auth.tokens()
    ]


@router.post("", status_code=201)
async def create_token(payload: TokenCreate, state: State) -> TokenCreated:
    stored, token = state.auth.add_token(payload.name, datetime.now(UTC))
    return TokenCreated(id=stored.id, name=stored.name, token=token)


@router.delete("/{token_id}", status_code=204)
async def delete_token(token_id: str, state: State) -> Response:
    if not state.auth.revoke(token_id):
        raise RouteError(404, "token_not_found", f"no token {token_id}")
    return Response(status_code=204)

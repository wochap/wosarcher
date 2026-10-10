"""`wosarcher tokens new|list|revoke`: API tokens, through the token routes (socket or browser session only)."""

import os
from typing import Annotated

import typer
from pydantic import TypeAdapter
from rich.console import Console
from rich.table import Table

from wosarcher.cli.api import api
from wosarcher.models import TokenCreate, TokenCreated, TokenInfo

tokens_app = typer.Typer(no_args_is_help=True, help="Create, list, and revoke API tokens.")


@tokens_app.command("new")
def new(name: str) -> None:
    """Create an API token named NAME and print it; it is shown only once."""
    body = TokenCreate(name=name).model_dump()
    created = TokenCreated.model_validate(api(os.environ).ok("POST", "/api/tokens", json=body).json())
    typer.echo(created.token)
    Console(stderr=True).print(f"token {created.id} ({name}) created; it is not shown again", markup=False)


@tokens_app.command("list")
def list_tokens() -> None:
    """List API tokens, masked to their last 4 characters."""
    table = Table("id", "name", "token", "created", "last used")
    for token in TypeAdapter(list[TokenInfo]).validate_python(api(os.environ).get("/api/tokens")):
        last_used = token.last_used.isoformat(timespec="seconds") if token.last_used else ""
        table.add_row(token.id, token.name, token.masked, token.created.isoformat(timespec="seconds"), last_used)
    Console(highlight=False).print(table)


@tokens_app.command("revoke")
def revoke(token_id: Annotated[str, typer.Argument(metavar="ID")]) -> None:
    """Revoke the API token with ID; the daemon rejects it at once."""
    api(os.environ).ok("DELETE", f"/api/tokens/{token_id}")
    typer.echo(f"token {token_id} revoked")

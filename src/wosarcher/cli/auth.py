"""`wosarcher auth`: the admin password and API tokens, stored in `auth.json` in the config directory."""

import os
from datetime import UTC, datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from wosarcher.auth import AuthStore, hash_password, masked
from wosarcher.cli import fail
from wosarcher.config import ConfigError, Settings, config_dir, resolve

auth_app = typer.Typer(no_args_is_help=True, help="Set the admin password and manage API tokens.")

MIN_LENGTH = 8


def settings() -> Settings:
    try:
        return resolve(None, [], os.environ)
    except ConfigError as error:
        raise fail(error, 2) from None


def store() -> AuthStore:
    return AuthStore.from_settings(settings(), config_dir(os.environ))


@auth_app.command("set-password")
def set_password(
    print_: Annotated[
        bool, typer.Option("--print", help="Print the hash for WOSARCHER_AUTH__PASSWORD_HASH instead of storing it.")
    ] = False,
) -> None:
    """Prompt for the admin password and store its scrypt hash; this ends every browser session."""
    password = typer.prompt("Password", hide_input=True)
    if typer.prompt("Repeat password", hide_input=True) != password:
        raise fail(ValueError("passwords do not match; nothing stored"))
    if len(password) < MIN_LENGTH:
        raise fail(ValueError(f"password must have at least {MIN_LENGTH} characters; nothing stored"))
    hashed = hash_password(password)
    if print_:
        typer.echo(hashed)
        return
    target = store()
    target.set_password(hashed)
    typer.echo(f"password stored in {target.path}")
    if target.env_hash is not None:
        Console(stderr=True).print(
            "warning: auth.password_hash is set (WOSARCHER_AUTH__PASSWORD_HASH or a profile) and takes precedence",
            markup=False,
            highlight=False,
        )


@auth_app.command("new-token")
def new_token(name: str) -> None:
    """Create an API token named NAME and print it; it is shown only once."""
    stored, token = store().add_token(name, datetime.now(UTC))
    typer.echo(token)
    Console(stderr=True).print(f"token {stored.id} ({name}) created; it is not shown again", markup=False)


@auth_app.command("list-tokens")
def list_tokens() -> None:
    """List API tokens, masked to their last 4 characters."""
    table = Table("id", "name", "token", "created", "last used")
    for token in store().tokens():
        last_used = token.last_used.isoformat(timespec="seconds") if token.last_used else ""
        table.add_row(token.id, token.name, masked(token.last4), token.created.isoformat(timespec="seconds"), last_used)
    Console(highlight=False).print(table)


@auth_app.command("revoke-token")
def revoke_token(token_id: Annotated[str, typer.Argument(metavar="ID")]) -> None:
    """Revoke the API token with ID; a running server rejects it at once."""
    if not store().revoke(token_id):
        raise fail(ValueError(f"no token {token_id}"))
    typer.echo(f"token {token_id} revoked")

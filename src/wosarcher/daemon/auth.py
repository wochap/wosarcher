"""`wosarcherd auth set-password`: the admin password, stored in `auth.json` (mode 0600) in the config directory.

API tokens are managed through the server (`wosarcher tokens`).
"""

import os
from typing import Annotated

import typer
from rich.console import Console

from wosarcher.auth import AuthStore, hash_password
from wosarcher.cli.options import fail
from wosarcher.config import ConfigError, config_dir, resolve

auth_app = typer.Typer(no_args_is_help=True, help="Set the admin password.")

MIN_LENGTH = 8


def store() -> AuthStore:
    try:
        settings = resolve(None, [], os.environ)
    except ConfigError as error:
        raise fail(error, 2) from None
    return AuthStore.from_settings(settings, config_dir(os.environ))


@auth_app.command("set-password")
def set_password(
    print_: Annotated[
        bool, typer.Option("--print", help="Print the hash for WOSARCHER_AUTH__PASSWORD_HASH instead of storing it.")
    ] = False,
) -> None:
    """Prompt for the admin password and store its scrypt hash; this ends every browser session."""
    password = typer.prompt("Password", hide_input=True)
    if typer.prompt("Repeat password", hide_input=True) != password:
        raise fail("passwords do not match; nothing stored")
    if len(password) < MIN_LENGTH:
        raise fail(f"password must have at least {MIN_LENGTH} characters; nothing stored")
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

"""Command line: `wosarcher profile list|show|use` and `wosarcher schema`."""

import json
import os
from typing import Annotated

import typer
from pydantic.json_schema import models_json_schema
from rich.console import Console

from wosarcher.config import ConfigError, list_profiles, redact, resolve, select_profile, store_profile, to_toml
from wosarcher.models import CONTRACTS

app = typer.Typer(no_args_is_help=True, add_completion=False)
profile_app = typer.Typer(no_args_is_help=True, help="List, show, and choose configuration profiles.")
app.add_typer(profile_app, name="profile")

ProfileOption = Annotated[str | None, typer.Option("--profile", help="Profile to use for this command.")]
SetOption = Annotated[list[str] | None, typer.Option("--set", help="Override one field: dotted.key=value.")]


def fail(error: ConfigError) -> typer.Exit:
    Console(stderr=True).print(f"error: {error}", markup=False, highlight=False)
    return typer.Exit(1)


@profile_app.command("list")
def profile_list(profile: ProfileOption = None) -> None:
    """List profiles with their source; `*` marks the active one."""
    env = os.environ
    active = select_profile(profile, env)
    for name, (_, source) in list_profiles(env).items():
        typer.echo(f"{'*' if name == active else ' '} {name}  ({source})")


@profile_app.command("show")
def profile_show(name: Annotated[str | None, typer.Argument()] = None, set_: SetOption = None) -> None:
    """Print the fully resolved configuration, secrets redacted."""
    try:
        settings = resolve(name, set_ or [], os.environ)
    except ConfigError as error:
        raise fail(error) from None
    typer.echo(to_toml(redact(settings)), nl=False)


@profile_app.command("use")
def profile_use(name: str) -> None:
    """Make NAME the default profile."""
    try:
        store_profile(name, os.environ)
    except ConfigError as error:
        raise fail(error) from None
    typer.echo(f"default profile: {name}")


@app.command()
def schema() -> None:
    """Print the JSON Schema of every contract type."""
    _, document = models_json_schema([(model, "validation") for model in CONTRACTS], title="wosarcher contracts")
    typer.echo(json.dumps(document, indent=2, sort_keys=True))


def main() -> None:
    app()

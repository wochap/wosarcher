"""Command line: `profile list|show|use`, `doctor`, `schema`; `run`, `fork`, `runs`, and `serve` are in submodules."""

import asyncio
import json
import os
from typing import Annotated

import httpx
import typer
from pydantic.json_schema import models_json_schema
from rich.console import Console
from rich.table import Table

import wosarcher.doctor as health
from wosarcher.build import build
from wosarcher.config import (
    ConfigError,
    Settings,
    list_profiles,
    redact,
    resolve,
    select_profile,
    store_profile,
    to_toml,
)
from wosarcher.http import UsageLedger
from wosarcher.models import CONTRACTS, DoctorReport

app = typer.Typer(no_args_is_help=True, add_completion=False)
profile_app = typer.Typer(no_args_is_help=True, help="List, show, and choose configuration profiles.")
app.add_typer(profile_app, name="profile")

ProfileOption = Annotated[str | None, typer.Option("--profile", help="Profile to use for this command.")]
SetOption = Annotated[list[str] | None, typer.Option("--set", help="Override one field: dotted.key=value.")]


def fail(error: Exception, code: int = 1) -> typer.Exit:
    Console(stderr=True, soft_wrap=True).print(f"error: {error}", markup=False, highlight=False)
    return typer.Exit(code)


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


async def check_providers(settings: Settings) -> DoctorReport:
    async with httpx.AsyncClient() as http:
        try:
            adapters = build(settings, http, UsageLedger({}))
        except ValueError as error:
            raise ConfigError(str(error)) from None
        return await health.check(settings, adapters.managed)


def render(report: DoctorReport) -> None:
    table = Table("block", "provider", "base URL", "device", "status", "model", "latency ms", "unload")
    for column in table.columns:
        column.overflow = "fold"
    for row in report.providers:
        latency = f"{row.latency_ms:.0f}" if row.latency_ms is not None else ""
        status = "built in" if row.status == "built-in" else row.status
        cells = [row.block, row.provider, row.base_url, row.device or "", status, row.model or "", latency, row.unload]
        table.add_row(*cells)
    console = Console(highlight=False)
    console.print(table)
    for row in report.providers:
        if row.error:
            console.print(f"{row.block}: {row.error}", markup=False)
    for warning in report.warnings:
        console.print(f"warning: {warning}", markup=False)


@app.command()
def doctor(
    profile: ProfileOption = None,
    set_: SetOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Check that every configured provider answers, which model it serves, and whether it can unload.

    Each remote block gets one small real request. The Firecrawl probe scrapes
    https://example.com, which spends one credit on the cloud API.
    Exit code 1 when any probe fails.
    """
    try:
        settings = resolve(profile, set_ or [], os.environ)
        report = asyncio.run(check_providers(settings))
    except ConfigError as error:
        raise fail(error) from None
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render(report)
    if any(row.status == "failed" for row in report.providers):
        raise typer.Exit(1)


@app.command()
def schema() -> None:
    """Print the JSON Schema of every contract type."""
    _, document = models_json_schema([(model, "validation") for model in CONTRACTS], title="wosarcher contracts")
    typer.echo(json.dumps(document, indent=2, sort_keys=True))


def main() -> None:
    app()


from wosarcher.cli import run as run_commands  # noqa: E402  (registers run, fork, runs on `app`)
from wosarcher.cli import serve as serve_command  # noqa: E402

app.command("run")(run_commands.run)
app.command("fork")(run_commands.fork)
app.command("runs")(run_commands.runs)
app.command("serve")(serve_command.serve)

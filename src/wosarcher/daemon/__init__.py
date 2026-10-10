"""`wosarcherd`: the daemon (`serve`), the engine commands it spawns (`run`, `fork`, `doctor`), and local admin.

Only this command reads profiles, secrets, `auth.json`, and run directories;
`wosarcher` is a client of its API.
"""

import asyncio
import os
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.table import Table

import wosarcher.doctor as health
from wosarcher.build import build
from wosarcher.cli.options import ProfileOption, SetOption, fail
from wosarcher.config import ConfigError, Settings, resolve, store_profile
from wosarcher.daemon import run as run_commands
from wosarcher.daemon import serve as serve_command
from wosarcher.daemon.auth import auth_app
from wosarcher.http import UsageLedger
from wosarcher.models import DoctorReport

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
profile_app = typer.Typer(no_args_is_help=True, help="Choose the default profile.")
app.add_typer(profile_app, name="profile")


@profile_app.command("use")
def profile_use(name: str) -> None:
    """Make NAME the default profile."""
    try:
        store_profile(name, os.environ)
    except ConfigError as error:
        raise fail(error, 2) from None
    typer.echo(f"default profile: {name}")


async def check_providers(settings: Settings, chosen: list[str] | None = None) -> DoctorReport:
    async with httpx.AsyncClient() as http:
        try:
            adapters = build(settings, http, UsageLedger({}))
        except ValueError as error:
            raise ConfigError(str(error)) from None
        return await health.check(settings, adapters.managed, chosen)


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
    for row in report.providers:
        if row.note:
            console.print(f"{row.block}: {row.note}", markup=False)
    for warning in report.warnings:
        console.print(f"warning: {warning}", markup=False)


@app.command()
def doctor(
    profile: ProfileOption = None,
    set_: SetOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
    block: Annotated[list[str] | None, typer.Option("--block", help="Check only this block; repeat for more.")] = None,
) -> None:
    """Check that every configured provider answers, which model it serves, and whether it can unload.

    Each remote block gets one small real request. The Firecrawl probe scrapes
    https://example.com, which spends one credit on the cloud API.
    Exit code 1 when any probe fails.
    """
    unknown = [name for name in block or [] if name not in health.BLOCKS]
    if unknown:
        raise fail(f"unknown block {', '.join(unknown)}; choose from {', '.join(health.BLOCKS)}")
    try:
        settings = resolve(profile, set_ or [], os.environ)
        report = asyncio.run(check_providers(settings, block or None))
    except ConfigError as error:
        raise fail(error) from None
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render(report)
    if any(row.status == "failed" for row in report.providers):
        raise typer.Exit(1)


app.command("serve")(serve_command.serve)
app.command("run")(run_commands.run)
app.command("fork")(run_commands.fork)
app.add_typer(auth_app, name="auth")


def main() -> None:
    app()

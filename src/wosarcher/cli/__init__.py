"""`wosarcher`: a client of the `wosarcherd` API; it holds no secret and reads no run directory.

Commands: `run`, `fork`, `runs`, `logs`, `cancel`, `export`, `doctor`,
`profile list|show`, `depth list|show`, `tokens new|list|revoke`, `schema`.
"""

import json
import os
from typing import Annotated, Any

import typer
from pydantic import TypeAdapter
from pydantic.json_schema import models_json_schema
from rich.console import Console
from rich.table import Table

from wosarcher.cli import export as export_command
from wosarcher.cli import logs as logs_command
from wosarcher.cli import run as run_commands
from wosarcher.cli.api import api
from wosarcher.cli.depth import depth_app
from wosarcher.cli.options import ProfileOption, fail
from wosarcher.cli.tokens import tokens_app
from wosarcher.config import to_toml
from wosarcher.models import CONTRACTS, HealthCheckRequest, HealthReport, ProfileInfo

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
profile_app = typer.Typer(no_args_is_help=True, help="List and show the daemon's configuration profiles.")
app.add_typer(profile_app, name="profile")


def profiles() -> list[ProfileInfo]:
    return TypeAdapter(list[ProfileInfo]).validate_python(api(os.environ).get("/api/profiles"))


@profile_app.command("list")
def profile_list() -> None:
    """List profiles with their source and description; `*` marks the active one."""
    for info in profiles():
        line = f"{'*' if info.active else ' '} {info.name}  ({info.source})"
        typer.echo(f"{line}  {info.description}" if info.description else line)


@profile_app.command("show")
def profile_show(name: Annotated[str | None, typer.Argument()] = None) -> None:
    """Print the profile's resolved configuration as the daemon sees it, secrets redacted."""
    found = profiles()
    info = next((p for p in found if p.name == name), None) if name else next((p for p in found if p.active), None)
    if info is None:
        raise fail(f"unknown profile '{name}'; available: {', '.join(p.name for p in found)}", 2)
    if info.settings is None:
        raise fail(f"profile '{info.name}' does not resolve on the daemon", 2)
    settings: dict[str, Any] = info.settings
    typer.echo(to_toml(settings), nl=False)


def render(report: HealthReport) -> None:
    table = Table("block", "provider", "URL", "device", "status", "model", "latency ms")
    for column in table.columns:
        column.overflow = "fold"
    for check in report.checks:
        latency = f"{check.latency_ms:.0f}" if check.latency_ms is not None else ""
        cells = [check.role, check.provider, check.url, check.device or "", check.status, check.model or "", latency]
        table.add_row(*cells)
    console = Console(highlight=False)
    console.print(table)
    for check in report.checks:
        if check.detail:
            console.print(f"{check.role}: {check.detail}", markup=False)
    for warning in report.warnings:
        console.print(f"warning: {warning}", markup=False)


@app.command()
def doctor(
    profile: ProfileOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
    block: Annotated[list[str] | None, typer.Option("--block", help="Check only this block; repeat for more.")] = None,
) -> None:
    """Ask the daemon to check its providers and print the report; exit code 1 when any block is down."""
    params = {"profile": profile} if profile else {}
    body = HealthCheckRequest(blocks=block or []).model_dump()
    response = api(os.environ).ok("POST", "/api/providers/health/check", params=params, json=body)
    report = HealthReport.model_validate_json(response.content)
    if block:
        report = report.model_copy(update={"checks": [check for check in report.checks if check.role in block]})
    if as_json:
        typer.echo(report.model_dump_json(indent=2))
    else:
        render(report)
    if any(check.status == "down" for check in report.checks):
        raise typer.Exit(1)


@app.command()
def schema() -> None:
    """Print the JSON Schema of every contract type."""
    _, document = models_json_schema([(model, "validation") for model in CONTRACTS], title="wosarcher contracts")
    typer.echo(json.dumps(document, indent=2, sort_keys=True))


app.command("run")(run_commands.run)
app.command("fork")(run_commands.fork)
app.command("runs")(run_commands.runs)
app.command("logs")(logs_command.logs)
app.command("cancel")(run_commands.cancel)
app.command("export")(export_command.export)
app.add_typer(depth_app, name="depth")
app.add_typer(tokens_app, name="tokens")


def main() -> None:
    app()

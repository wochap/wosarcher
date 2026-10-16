"""`wosarcher`: a client of the `wosarcherd` API; it holds no secret and reads no run directory.

Commands: `run`, `catalog`, `fork`, `runs`, `logs`, `cancel`, `questions`, `continue`, `export`, `doctor`,
`profile list|show`, `providers list`, `depth list|show`, `tokens new|list|revoke`, `schema`.
"""

import json
import os
from typing import Annotated, Any

import typer
from pydantic import TypeAdapter
from pydantic.json_schema import models_json_schema
from rich.console import Console
from rich.table import Table

from wosarcher.cli import catalog as catalog_command
from wosarcher.cli import export as export_command
from wosarcher.cli import logs as logs_command
from wosarcher.cli import questions as questions_command
from wosarcher.cli import run as run_commands
from wosarcher.cli.api import api
from wosarcher.cli.depth import depth_app
from wosarcher.cli.options import ClientProfileOption, UseOption, fail, use_map
from wosarcher.cli.tokens import tokens_app
from wosarcher.config import BLOCKS, to_toml
from wosarcher.models import CONTRACTS, ProfileInfo, ProviderEntryInfo, ProvidersCheck, ProvidersReport

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
profile_app = typer.Typer(no_args_is_help=True, help="List and show the daemon's configuration profiles.")
app.add_typer(profile_app, name="profile")
providers_app = typer.Typer(no_args_is_help=True, help="List the daemon's provider entries.")
app.add_typer(providers_app, name="providers")


def profiles() -> list[ProfileInfo]:
    return TypeAdapter(list[ProfileInfo]).validate_python(api(os.environ).get("/api/profiles"))


def entries_line(info: ProfileInfo) -> str:
    """The entries a profile uses, `search · fetch · prefilter · score · llm`; `?` where one does not resolve."""
    use = info.use or {}
    return " · ".join(use.get(block) or "?" for block in BLOCKS)


@profile_app.command("list")
def profile_list() -> None:
    """List profiles with their source, entries, and description; `*` marks the active one."""
    for info in profiles():
        line = f"{'*' if info.active else ' '} {info.name}  ({info.source})  {entries_line(info)}"
        typer.echo(f"{line}  {info.description}" if info.description else line)


@profile_app.command("show")
def profile_show(name: Annotated[str | None, typer.Argument()] = None) -> None:
    """Print the profile's entries, its own values, and its resolved configuration, secrets redacted."""
    found = profiles()
    info = next((p for p in found if p.name == name), None) if name else next((p for p in found if p.active), None)
    if info is None:
        raise fail(f"unknown profile '{name}'; available: {', '.join(p.name for p in found) or 'none'}", 2)
    for block in BLOCKS:
        typer.echo(f"use.{block} = {json.dumps((info.use or {}).get(block))}")
    if info.settings is None:
        raise fail(f"profile '{info.name}' does not resolve on the daemon: {info.error}", 2)
    own = {"llm.model": info.model, "search.allow_domains": info.allow_domains}
    own |= {"search.block_domains": info.block_domains}
    for model in info.models:
        tuning = model.model_dump(exclude={"id", "reasoning"}, exclude_none=True)
        tuning |= {f"reasoning.{step}": level for step, level in model.reasoning.model_dump(exclude_none=True).items()}
        own |= {f"models.{model.id}.{key}": value for key, value in tuning.items()}
    for key, value in own.items():
        if value is not None:
            typer.echo(f"{key} = {json.dumps(value)}")
    typer.echo("")
    settings: dict[str, Any] = info.settings
    typer.echo(to_toml(settings), nl=False)


@providers_app.command("list")
def providers_list(
    block: Annotated[str | None, typer.Option("--block", help=f"Only this block: {', '.join(BLOCKS)}.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the GET /api/providers answer.")] = False,
) -> None:
    """List the daemon's provider entries by block; llm entries with their models."""
    if block is not None and block not in BLOCKS:
        raise fail(f"unknown block '{block}'; choose from {', '.join(BLOCKS)}", 2)
    report = ProvidersReport.model_validate(api(os.environ).get("/api/providers"))
    entries = [info for info in report.entries if block is None or info.block == block]
    if as_json:
        typer.echo(report.model_copy(update={"entries": entries}).model_dump_json(indent=2))
        return
    for name in BLOCKS:
        found = [info for info in entries if info.block == name]
        if block is None and found:
            typer.echo(f"{name}:")
        for info in found:
            indent = "  " if block is None else ""
            source = "built-in" if info.source == "builtin" else info.source
            line = f"{indent}{info.name}  ({source})  {info.provider}"
            detail = (info.error and f"error: {info.error}") or info.description
            typer.echo(f"{line}  {detail}" if detail else line)
            for model in info.models:
                mark = "  (default)" if model.id == info.model else ""
                limits = f"{model.context_window or '-'} / {model.max_output_tokens or '-'}"
                typer.echo(f"{indent}    {model.id}{mark}  {limits}")


def render(rows: list[ProviderEntryInfo], warnings: list[str]) -> None:
    table = Table("block", "entry", "provider", "URL", "device", "status", "model", "latency ms")
    for column in table.columns:
        column.overflow = "fold"
    for row in rows:
        latency = f"{row.latency_ms:.0f}" if row.latency_ms is not None else ""
        cells = [row.block, row.name, row.provider, row.url, row.device or "", row.status, row.model, latency]
        table.add_row(*cells)
    console = Console(highlight=False)
    console.print(table)
    for row in rows:
        if row.detail or row.error:
            console.print(f"{row.block}/{row.name}: {row.error or row.detail}", markup=False)
    for warning in warnings:
        console.print(f"warning: {warning}", markup=False)


@app.command()
def doctor(
    profile: ClientProfileOption = None,
    use: UseOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
    block: Annotated[list[str] | None, typer.Option("--block", help="Check only this block; repeat for more.")] = None,
) -> None:
    """Ask the daemon to check the profile's provider entries and print them; exit code 1 when any is down."""
    unknown = [name for name in block or [] if name not in BLOCKS]
    if unknown:
        raise fail(f"unknown block {', '.join(unknown)}; choose from {', '.join(BLOCKS)}", 2)
    found = profiles()
    info = (
        next((p for p in found if p.name == profile), None) if profile else next((p for p in found if p.active), None)
    )
    if info is None:
        raise fail(f"unknown profile '{profile}'; available: {', '.join(p.name for p in found) or 'none'}", 2)
    chosen = {**(info.use or {}), **use_map(use)}
    missing = [name for name in BLOCKS if (block is None or name in block) and not chosen.get(name)]
    if missing:
        raise fail(f"profile '{info.name}' names no entry for {', '.join(missing)}; add --use", 2)
    names = [f"{name}/{chosen[name]}" for name in BLOCKS if block is None or name in block]
    body = ProvidersCheck(entries=names).model_dump()
    response = api(os.environ).ok("POST", "/api/providers/check", json=body)
    report = ProvidersReport.model_validate_json(response.content)
    rows = [row for name in names for row in report.entries if f"{row.block}/{row.name}" == name]
    if as_json:
        typer.echo(report.model_copy(update={"profile": info.name, "entries": rows}).model_dump_json(indent=2))
    else:
        render(rows, report.warnings)
    if any(row.status == "down" for row in rows):
        raise typer.Exit(1)


@app.command()
def schema() -> None:
    """Print the JSON Schema of every contract type."""
    _, document = models_json_schema([(model, "validation") for model in CONTRACTS], title="wosarcher contracts")
    typer.echo(json.dumps(document, indent=2, sort_keys=True))


app.command("run")(run_commands.run)
app.command("catalog")(catalog_command.catalog)
app.command("fork")(run_commands.fork)
app.command("runs")(run_commands.runs)
app.command("logs")(logs_command.logs)
app.command("cancel")(run_commands.cancel)
app.command("questions")(questions_command.questions)
app.command("continue")(questions_command.continue_)
app.command("export")(export_command.export)
app.add_typer(depth_app, name="depth")
app.add_typer(tokens_app, name="tokens")


def main() -> None:
    app()

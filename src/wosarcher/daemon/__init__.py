"""`wosarcherd`: the daemon (`serve`), the engine commands it spawns (`run`, `fork`, `doctor`), and local admin.

Only this command reads profiles, secrets, `auth.json`, and run directories;
`wosarcher` is a client of its API.
"""

import asyncio
import os
from typing import Annotated, Literal

import httpx
import typer
from rich.console import Console
from rich.table import Table

import wosarcher.doctor as health
from wosarcher.build import build
from wosarcher.cli.options import ProfileOption, SetOption, UseOption, fail, use_map
from wosarcher.config import (
    ConfigError,
    Settings,
    entry_settings,
    list_entries,
    resolve,
    resolve_run,
    store_profile,
    use_overrides,
)
from wosarcher.daemon import run as run_commands
from wosarcher.daemon import serve as serve_command
from wosarcher.daemon.auth import auth_app
from wosarcher.http import UsageLedger
from wosarcher.models import DoctorReport, ProviderHealth

GpuPolicy = Literal["shared", "exclusive"]

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


Checked = tuple[str, str, Settings]
"""A block, an entry name, and settings holding that entry."""


async def check_entries(items: list[Checked], gpu_policy: GpuPolicy) -> DoctorReport:
    """One row per entry: cloud entries concurrently, local ones one at a time beside them."""
    warnings: list[str] = []

    async def one(item: Checked, release: bool) -> ProviderHealth:
        block, name, settings = item
        async with httpx.AsyncClient() as http:
            try:
                adapters = build(settings, http, UsageLedger({}))
            except ValueError as error:
                raise ConfigError(f"{block}/{name}: {error}") from None
            report = await health.check(settings, adapters.managed, [block])
            warnings.extend(f"{block}/{name}: {warning}" for warning in report.warnings)
            row = report.providers[0].model_copy(update={"entry": name})
            if release and row.unload == "yes":
                try:
                    await adapters.managed[block].release()
                except Exception as error:
                    warnings.append(f"{block}/{name} release failed: {error}")
            return row

    local = [index for index, (block, _, settings) in enumerate(items) if health.is_local(getattr(settings, block))]
    cloud = [index for index in range(len(items)) if index not in local]

    async def chain() -> list[ProviderHealth]:
        exclusive = gpu_policy == "exclusive"
        return [await one(items[index], exclusive and index != local[-1]) for index in local]

    cloud_rows, local_rows = await asyncio.gather(
        asyncio.gather(*(one(items[index], False) for index in cloud)), chain()
    )
    rows = dict(zip([*cloud, *local], [*cloud_rows, *local_rows], strict=True))
    providers = tuple(rows[index] for index in range(len(items)))
    return DoctorReport(gpu_policy=gpu_policy, providers=providers, warnings=tuple(warnings))


def entry_items(entry: list[str], all_entries: bool, profile: str | None) -> tuple[list[Checked], GpuPolicy]:
    """The entries to check, each in its own settings, and the GPU policy of the selected profile."""
    env = os.environ
    try:
        policy = resolve(profile, [], env).run.gpu_policy
    except ConfigError:
        policy = "shared"
    if all_entries:
        names = [(block, name) for block, found in list_entries(env).items() for name in found]
    else:
        names = [(block, name) for block, name in use_pairs(entry)]
    return [(block, name, entry_settings(block, name, env, policy)) for block, name in names], policy


def use_pairs(values: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for value in values:
        block, sep, name = value.partition("=")
        if not sep or not name:
            raise ConfigError(f"--entry {value} must look like BLOCK=NAME")
        pairs.append((block, name))
    return pairs


def render(report: DoctorReport) -> None:
    table = Table("block", "entry", "provider", "base URL", "device", "status", "model", "latency ms", "unload")
    for column in table.columns:
        column.overflow = "fold"
    for row in report.providers:
        latency = f"{row.latency_ms:.0f}" if row.latency_ms is not None else ""
        status = "built in" if row.status == "built-in" else row.status
        cells = [row.block, row.entry or "", row.provider, row.base_url, row.device or "", status, row.model or ""]
        table.add_row(*cells, latency, row.unload)
    console = Console(highlight=False)
    console.print(table)
    for row in report.providers:
        if row.error:
            console.print(f"{row.block}/{row.entry}: {row.error}", markup=False)
    for row in report.providers:
        if row.note:
            console.print(f"{row.block}/{row.entry}: {row.note}", markup=False)
    for warning in report.warnings:
        console.print(f"warning: {warning}", markup=False)


@app.command()
def doctor(
    profile: ProfileOption = None,
    use: UseOption = None,
    set_: SetOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
    block: Annotated[list[str] | None, typer.Option("--block", help="Check only this block; repeat for more.")] = None,
    entry: Annotated[
        list[str] | None,
        typer.Option("--entry", metavar="BLOCK=NAME", help="Check this provider entry alone; repeat for more."),
    ] = None,
    all_entries: Annotated[bool, typer.Option("--all-entries", help="Check every provider entry.")] = False,
) -> None:
    """Check that every configured provider answers, which model it serves, and whether it can unload.

    Each remote block gets one small real request. The Firecrawl probe scrapes
    https://example.com, which spends one credit on the cloud API.
    Exit code 1 when any probe fails.
    """
    unknown = [name for name in block or [] if name not in health.BLOCKS]
    if unknown:
        raise fail(f"unknown block {', '.join(unknown)}; choose from {', '.join(health.BLOCKS)}")
    if (entry or all_entries) and (block or use):
        raise fail("--entry and --all-entries cannot be combined with --block or --use", 2)
    try:
        if entry or all_entries:
            items, policy = entry_items(entry or [], all_entries, profile)
            report = asyncio.run(check_entries(items, policy))
        else:
            resolved = resolve_run(profile, [*(set_ or []), *use_overrides(use_map(use))], os.environ)
            report = asyncio.run(check_providers(resolved.settings, block or None))
            rows = [row.model_copy(update={"entry": resolved.use[row.block]}) for row in report.providers]
            report = report.model_copy(update={"providers": tuple(rows)})
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

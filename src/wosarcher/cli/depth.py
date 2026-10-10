"""`wosarcher depth list|show`: the depth presets the daemon knows."""

import os

import typer
from pydantic import TypeAdapter

from wosarcher.cli.api import api
from wosarcher.cli.options import fail
from wosarcher.models import DepthInfo

depth_app = typer.Typer(no_args_is_help=True, help="List and show depth presets.")


def presets() -> list[DepthInfo]:
    return TypeAdapter(list[DepthInfo]).validate_python(api(os.environ).get("/api/depths"))


@depth_app.command("list")
def depth_list() -> None:
    """One line per preset: its name and description."""
    for preset in presets():
        typer.echo(f"{preset.name}  {preset.description}")


@depth_app.command("show")
def depth_show(name: str) -> None:
    """The values NAME runs with."""
    found = {preset.name: preset for preset in presets()}
    if name not in found:
        raise fail(f"unknown depth '{name}'; available: {', '.join(found)}", 2)
    for key, value in found[name].values.model_dump(exclude_none=True).items():
        typer.echo(f"{key} = {value}")

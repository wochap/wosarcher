"""`wosarcher depth list|show`: the built-in depth presets."""

from typing import Any

import typer

from wosarcher.cli import fail
from wosarcher.config import ConfigError, depth_values, list_depths, read_depth

depth_app = typer.Typer(no_args_is_help=True, help="List and show depth presets.")


def preset(name: str) -> tuple[str, dict[str, Any]]:
    try:
        _, description, data = read_depth(name)
    except ConfigError as error:
        raise fail(error, 2) from None
    return description, depth_values(data)


@depth_app.command("list")
def depth_list() -> None:
    """One line per preset: its name and description."""
    for name in list_depths():
        description, _ = preset(name)
        typer.echo(f"{name}  {description}")


@depth_app.command("show")
def depth_show(name: str) -> None:
    """The keys NAME sets, with their values."""
    _, values = preset(name)
    if not values:
        typer.echo("sets nothing; uses the defaults")
    for key, value in values.items():
        typer.echo(f"{key} = {value}")

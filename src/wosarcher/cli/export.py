"""`wosarcher export`: a finished report or answer as PDF or DOCX, converted by the daemon."""

import os
from pathlib import Path
from typing import Annotated, get_args

import typer

from wosarcher.cli.api import api
from wosarcher.cli.options import fail
from wosarcher.models import ExportFormat

FORMATS: tuple[str, ...] = get_args(ExportFormat)


def export(
    run_id: Annotated[str, typer.Argument(help="The run to export.")],
    format: Annotated[str, typer.Option("--format", help="pdf or docx.")],
    output: Annotated[Path | None, typer.Option("--output", help="File to write; default <run id>.<format>.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
) -> None:
    """Write a finished report or answer as PDF or DOCX and print the written path.

    Exit code 1 when a converter is missing on the daemon or the conversion fails, 2 for an
    unknown run or format, a run without a report, or an existing file without --force.
    """
    if format not in FORMATS:
        raise fail(f"format must be one of: {', '.join(FORMATS)}", 2)
    target = output or Path(f"{run_id}.{format}")
    if target.exists() and not force:
        raise fail(f"{target} already exists; pass --force to overwrite it", 2)
    response = api(os.environ).ok("GET", f"/api/runs/{run_id}/export", params={"format": format})
    target.write_bytes(response.content)
    typer.echo(str(target))

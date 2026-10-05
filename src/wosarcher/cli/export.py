"""`wosarcher export`: a finished report or answer as PDF or DOCX."""

import asyncio
import os
from pathlib import Path
from typing import Annotated, get_args

import typer

from wosarcher.build import exporter
from wosarcher.cli import ProfileOption, fail
from wosarcher.config import ConfigError, resolve
from wosarcher.document import document
from wosarcher.models import ExportFormat, Report
from wosarcher.ports import ExportError
from wosarcher.store import RunStore

FORMATS: tuple[str, ...] = get_args(ExportFormat)


def export(
    run_id: Annotated[str, typer.Argument(help="The run to export.")],
    format: Annotated[str, typer.Option("--format", help="pdf or docx.")],
    output: Annotated[Path | None, typer.Option("--output", help="File to write; default <run id>.<format>.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
    profile: ProfileOption = None,
) -> None:
    """Write a finished report or answer as PDF or DOCX and print the written path.

    Exit code 1 when a converter is missing or the conversion fails, 2 for an
    unknown run or format, a run without a report, or an existing file without --force.
    """
    if format not in FORMATS:
        raise fail(ValueError(f"format must be one of: {', '.join(FORMATS)}"), 2)
    fmt: ExportFormat = format  # pyright: ignore[reportAssignmentType]  (checked above)
    try:
        store = RunStore.from_settings(resolve(profile, [], os.environ))
    except ConfigError as error:
        raise fail(error, 2) from None
    run_dir = store.run_dir(run_id)
    if not (run_dir / "request.json").is_file():
        raise fail(ValueError(f"no run {run_id} in {store.runs_dir}"), 2)
    if not (run_dir / "report.json").is_file():
        raise fail(ValueError(f"run {run_id} has no report"), 2)
    target = output or Path(f"{run_id}.{fmt}")
    if target.exists() and not force:
        raise fail(ValueError(f"{target} already exists; pass --force to overwrite it"), 2)
    converter = exporter()
    missing = converter.missing(fmt)
    if missing:
        raise fail(ValueError(f"{fmt.upper()} export needs {' and '.join(missing)} on the server"))
    markdown = document(store.read_record(run_id), store.read_artifact(run_id, "report.json", Report))
    try:
        data = asyncio.run(converter.export(markdown, fmt))
    except ExportError as error:
        raise fail(error) from None
    target.write_bytes(data)
    typer.echo(str(target))

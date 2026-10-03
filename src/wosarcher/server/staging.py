"""Queued runs on disk (`runs/.queue/<id>/`) and the argv that starts each one.

A staged run holds everything its summary and its argv need, so the queue
survives a restart with no other state.
"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from wosarcher.models import (
    Attachment,
    ForkCreate,
    RunCreate,
    RunRecord,
    ServerSettings,
    Sources,
    Stage,
    WritingOptions,
    WritingPatch,
)
from wosarcher.store import new_run_id

QUEUE_DIR = ".queue"


class StagingError(Exception):
    pass


NO_ATTACHMENT = "sources files needs at least one attachment"


class StagedRun(RunCreate):
    """`runs/.queue/<id>/request.json`: the request plus what the server decided when it accepted it."""

    run_id: str
    kind: Literal["run", "fork", "rerun"]
    created: datetime
    resolved_sources: Sources
    resolved_profile: str
    writing_options: WritingOptions
    """The writing options the run will use (for its summary)."""
    writing_flags: dict[str, object] = Field(default_factory=dict[str, object])
    """Emitted as `--set write.<field>=...` before `set`."""
    parent: str | None = None
    from_stage: Stage | None = None
    version: int = 1


def queue_dir(runs_dir: Path) -> Path:
    return runs_dir / QUEUE_DIR


def staging_dir(runs_dir: Path, run_id: str) -> Path:
    return queue_dir(runs_dir) / run_id


def fresh_id(runs_dir: Path) -> str:
    while True:
        run_id = new_run_id()
        if not (runs_dir / run_id).exists() and not staging_dir(runs_dir, run_id).exists():
            return run_id


def merged(base: WritingOptions, patch: WritingPatch) -> WritingOptions:
    return base.model_copy(update=patch.model_dump(exclude_none=True))


def base_name(name: str) -> str:
    """The last path part of an uploaded file name, with Windows separators too."""
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    if name in ("", ".", ".."):
        raise StagingError(f"attachment name '{name}' is not a file name")
    return name


def write(runs_dir: Path, staged: StagedRun, uploads: list[Attachment]) -> StagedRun:
    names = [base_name(upload.name) for upload in uploads]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise StagingError(f"two attachments are named {', '.join(duplicates)}")
    path = staging_dir(runs_dir, staged.run_id)
    (path / "attachments").mkdir(parents=True, exist_ok=True)
    for name, upload in zip(names, uploads, strict=True):
        (path / "attachments" / name).write_bytes(upload.data)
    (path / "request.json").write_text(staged.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return staged


def stage_run(
    runs_dir: Path, request: RunCreate, uploads: list[Attachment], defaults: ServerSettings, profile: str
) -> StagedRun:
    """A new run: global settings below the request's sources and writing."""
    if (request.sources or defaults.sources) == "files" and not uploads:
        raise StagingError(NO_ATTACHMENT)
    staged = StagedRun(
        **request.model_dump(),
        run_id=fresh_id(runs_dir),
        kind="run",
        created=datetime.now(UTC),
        resolved_sources=request.sources or defaults.sources,
        resolved_profile=request.profile or profile,
        writing_options=merged(defaults.writing, request.writing),
        writing_flags=merged(defaults.writing, request.writing).model_dump(),
    )
    return write(runs_dir, staged, uploads)


def stage_fork(runs_dir: Path, parent: RunRecord, request: ForkCreate) -> StagedRun:
    """A fork keeps the parent's configuration; only the request's writing and `set` change it."""
    writing = WritingOptions.model_validate(parent.settings.get("write", {}))
    staged = StagedRun(
        query=parent.request.query,
        until=parent.request.until,
        profile=request.profile,
        writing=request.writing,
        set=request.set,
        run_id=fresh_id(runs_dir),
        kind="fork",
        created=datetime.now(UTC),
        resolved_sources=parent.request.sources,
        resolved_profile=request.profile or parent.profile,
        writing_options=merged(writing, request.writing),
        writing_flags=request.writing.model_dump(exclude_none=True),
        parent=parent.run_id,
        from_stage=request.from_stage,
        version=parent.version + 1,
    )
    return write(runs_dir, staged, [])


def stage_rerun(runs_dir: Path, original: RunRecord) -> StagedRun:
    """The original request and saved overrides, and a copy of its attachments; no global settings."""
    staged = StagedRun(
        query=original.request.query,
        sources=original.request.sources,
        until=original.request.until,
        profile=original.profile,
        set=original.overrides,
        run_id=fresh_id(runs_dir),
        kind="rerun",
        created=datetime.now(UTC),
        resolved_sources=original.request.sources,
        resolved_profile=original.profile,
        writing_options=WritingOptions.model_validate(original.settings.get("write", {})),
    )
    path = staging_dir(runs_dir, staged.run_id)
    attachments = runs_dir / original.run_id / "attachments"
    if attachments.is_dir():
        shutil.copytree(attachments, path / "attachments")
    copied = (path / "attachments").is_dir() and any((path / "attachments").iterdir())
    if staged.resolved_sources == "files" and not copied:
        remove(runs_dir, staged.run_id)
        raise StagingError(NO_ATTACHMENT)
    return write(runs_dir, staged, [])


def read_staged(runs_dir: Path) -> list[StagedRun]:
    """Every staged run, oldest first."""
    found = [
        StagedRun.model_validate_json((path / "request.json").read_text(encoding="utf-8"))
        for path in sorted(queue_dir(runs_dir).glob("*"))
        if (path / "request.json").is_file()
    ]
    return sorted(found, key=lambda staged: staged.created)


def remove(runs_dir: Path, run_id: str) -> None:
    shutil.rmtree(staging_dir(runs_dir, run_id), ignore_errors=True)


# Argv


def toml_value(value: object) -> str:
    """Strings as JSON strings (valid TOML basic strings), so a value with spaces stays one value."""
    return json.dumps(value)


def attach_flags(path: Path) -> list[str]:
    folder = path / "attachments"
    entries = sorted(folder.iterdir()) if folder.is_dir() else []
    return [flag for entry in entries for flag in ("--attach", str(entry))]


def set_flags(staged: StagedRun) -> list[str]:
    writing = [f"write.{name}={toml_value(value)}" for name, value in staged.writing_flags.items()]
    return [flag for value in [*writing, *staged.set] for flag in ("--set", value)]


def build_run_argv(command: list[str], staged: StagedRun, path: Path) -> list[str]:
    argv = [*command, "run", staged.query, "--run-id", staged.run_id, "--sources", staged.resolved_sources]
    if staged.until:
        argv += ["--until", staged.until]
    if staged.profile:
        argv += ["--profile", staged.profile]
    return argv + attach_flags(path) + set_flags(staged)


def build_fork_argv(command: list[str], staged: StagedRun) -> list[str]:
    assert staged.parent is not None
    assert staged.from_stage is not None
    argv = [*command, "fork", staged.parent, "--from", staged.from_stage, "--run-id", staged.run_id]
    if staged.profile:
        argv += ["--profile", staged.profile]
    return argv + set_flags(staged)


def build_rerun_argv(command: list[str], staged: StagedRun, path: Path) -> list[str]:
    argv = [*command, "run", staged.query, "--run-id", staged.run_id, "--sources", staged.resolved_sources]
    if staged.until:
        argv += ["--until", staged.until]
    argv += ["--profile", staged.resolved_profile]
    return argv + attach_flags(path) + [flag for value in staged.set for flag in ("--set", value)]


def build_argv(command: list[str], staged: StagedRun, runs_dir: Path) -> list[str]:
    path = staging_dir(runs_dir, staged.run_id)
    if staged.kind == "fork":
        return build_fork_argv(command, staged)
    if staged.kind == "rerun":
        return build_rerun_argv(command, staged, path)
    return build_run_argv(command, staged, path)

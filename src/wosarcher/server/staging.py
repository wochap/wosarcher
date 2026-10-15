"""Queued runs on disk (`runs/.queue/<id>/`) and the argv that starts each one.

A staged run holds everything its summary and its argv need, so the queue
survives a restart with no other state.
"""

import json
import os
import shutil
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from wosarcher.config import CUSTOM_DEPTH, LLM_KEYS, RESEARCH_KEYS, depth_values, load_depth, without_use
from wosarcher.models import (
    Attachment,
    ForkCreate,
    LimitsPatch,
    LLMPatch,
    Origin,
    ReuseAttachments,
    RunCreate,
    RunRecord,
    ServerSettings,
    Sources,
    Stage,
    WritingOptions,
    WritingPatch,
    catalog_writes,
)
from wosarcher.store import new_run_id

QUEUE_DIR = ".queue"


class StagingError(Exception):
    pass


class OverrideError(StagingError):
    """An override the API may not set."""


def check_overrides(overrides: list[str]) -> None:
    """Refuse `*_file` and `*_command` settings: they would read a file or run a command as the server."""
    for override in overrides:
        key = override.partition("=")[0].strip()
        if key.rpartition(".")[2].endswith(("_file", "_command")):
            raise OverrideError(f"{key} cannot be set through the API")


NO_ATTACHMENT = "sources files needs at least one attachment"


class StagedRun(RunCreate):
    """`runs/.queue/<id>/request.json`: the request plus what the server decided when it accepted it."""

    run_id: str
    action: Literal["run", "fork", "rerun"]
    created: datetime
    resolved_sources: Sources
    resolved_profile: str
    writing_options: WritingOptions
    """The writing options the run will use (for its summary)."""
    writing_flags: dict[str, object] = Field(default_factory=dict[str, object])
    """Emitted as `--set write.<field>=...` before `set`."""
    domain_flags: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    """`search.allow_domains` and `search.block_domains` overrides, emitted after research and before `set`."""
    parent: str | None = None
    from_stage: Stage | None = None
    version: int = 1
    origin: Origin = "web"
    token_name: str | None = None
    form: RunCreate | None = None
    """Recorded in the run's `request.json`; None for forks."""
    limits: LimitsPatch = LimitsPatch()
    """A catalog fork's raised limits, emitted as the limit flags."""

    @model_validator(mode="before")
    @classmethod
    def legacy_action(cls, data: Any) -> Any:
        """Staged runs written before run kinds existed hold the action in `kind`."""
        if not isinstance(data, dict):
            return data
        fields = cast(dict[str, Any], data)
        if "action" not in fields and fields.get("kind") in ("run", "fork", "rerun"):
            return {**fields, "action": fields["kind"], "kind": "research"}
        return fields


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


def preset_words(depth: str | None) -> WritingPatch:
    """The preset's `write.words`, as a patch between the global settings and the request."""
    if depth is None or depth == CUSTOM_DEPTH:
        return WritingPatch()
    _, data = load_depth(depth, os.environ)
    return WritingPatch(words=depth_values(data).get("write.words"))


DOMAIN_KEYS = {"allow": "search.allow_domains", "block": "search.block_domains"}


def domain_lists(request: RunCreate, defaults: ServerSettings, own: Collection[str]) -> dict[str, list[str]]:
    """The request's lists; else a non-empty global list whose key the profile and environment leave unset."""
    lists: dict[str, list[str]] = {}
    for field, key in DOMAIN_KEYS.items():
        given: list[str] | None = getattr(request.domains, field)
        default: list[str] = getattr(defaults.domains, field)
        if given is not None:
            lists[key] = given
        elif default and key not in own:
            lists[key] = default
    return lists


def base_name(name: str) -> str:
    """The last path part of an uploaded file name, with Windows separators too."""
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    if name in ("", ".", ".."):
        raise StagingError(f"attachment name '{name}' is not a file name")
    return name


class UnknownRunError(StagingError):
    """`reuse_attachments` names a run that does not exist."""


def attachments_dir(runs_dir: Path, run_id: str) -> Path | None:
    """The run directory's `attachments/`, or the staged one while the run is queued; None for no such run."""
    if run_id != base_name(run_id) or run_id.startswith("."):
        return None
    for path in (runs_dir / run_id, staging_dir(runs_dir, run_id)):
        if (path / "request.json").is_file():
            return path / "attachments"
    return None


def reused_files(runs_dir: Path, reuse: ReuseAttachments | None) -> list[Path]:
    """The files `reuse_attachments` names, checked to exist."""
    if reuse is None:
        return []
    folder = attachments_dir(runs_dir, reuse.run_id)
    if folder is None:
        raise UnknownRunError(f"run {reuse.run_id} not found")
    missing = [name for name in reuse.names if name != base_name(name) or not (folder / name).is_file()]
    if missing:
        raise StagingError(f"run {reuse.run_id} has no attachment named {', '.join(missing)}")
    return [folder / name for name in reuse.names]


def write(runs_dir: Path, staged: StagedRun, uploads: list[Attachment], reused: Sequence[Path] = ()) -> StagedRun:
    names = [base_name(upload.name) for upload in uploads] + [file.name for file in reused]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise StagingError(f"two attachments are named {', '.join(duplicates)}")
    path = staging_dir(runs_dir, staged.run_id)
    (path / "attachments").mkdir(parents=True, exist_ok=True)
    for name, upload in zip(names[: len(uploads)], uploads, strict=True):
        (path / "attachments" / name).write_bytes(upload.data)
    for file in reused:
        shutil.copyfile(file, path / "attachments" / file.name)
    (path / "request.json").write_text(staged.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return staged


def stage_run(
    runs_dir: Path,
    request: RunCreate,
    uploads: list[Attachment],
    defaults: ServerSettings,
    profile: str,
    own: Collection[str] = (),
    origin: Origin = "web",
    token_name: str | None = None,
) -> StagedRun:
    """A new run: global settings, then the depth preset's words, below the request's sources and writing.

    `own`: what the run's profile and the environment set; a global domain list yields to it.
    """
    check_overrides(request.set)
    reused = reused_files(runs_dir, request.reuse_attachments)
    if (request.sources or defaults.sources) == "files" and not uploads and not reused:
        raise StagingError(NO_ATTACHMENT)
    writing = merged(merged(defaults.writing, preset_words(request.depth)), request.writing)
    staged = StagedRun(
        **request.model_dump(),
        run_id=fresh_id(runs_dir),
        action="run",
        created=datetime.now(UTC),
        resolved_sources=request.sources or defaults.sources,
        resolved_profile=request.profile or profile,
        writing_options=writing,
        writing_flags=writing.model_dump() if request.kind == "research" or catalog_writes(request.structure) else {},
        domain_flags=domain_lists(request, defaults, own),
        origin=origin,
        token_name=token_name,
        form=request.model_copy(update={"set": []}),
    )
    return write(runs_dir, staged, uploads, reused)


def stage_fork(
    runs_dir: Path, parent: RunRecord, request: ForkCreate, origin: Origin = "web", token_name: str | None = None
) -> StagedRun:
    """A fork keeps the parent's configuration; only the request's writing and `set` change it."""
    check_overrides(request.set)
    writing = WritingOptions.model_validate(parent.settings.get("write", {}))
    staged = StagedRun(
        query=parent.request.query,
        kind=parent.kind,
        until=request.until,
        profile=request.profile,
        depth=parent.request.depth,
        writing=request.writing,
        llm=request.llm,
        use=request.use,
        set=request.set,
        run_id=fresh_id(runs_dir),
        action="fork",
        created=datetime.now(UTC),
        resolved_sources=parent.request.sources,
        resolved_profile=request.profile or parent.profile,
        writing_options=merged(writing, request.writing),
        writing_flags=request.writing.model_dump(exclude_none=True),
        limits=request.limits,
        parent=parent.run_id,
        from_stage=request.from_stage,
        version=parent.version + 1,
        origin=origin,
        token_name=token_name,
    )
    return write(runs_dir, staged, [])


def stage_rerun(
    runs_dir: Path, original: RunRecord, origin: Origin = "web", token_name: str | None = None
) -> StagedRun:
    """The original request, its five entries, saved overrides, and a copy of its attachments; no global settings."""
    check_overrides(original.overrides)
    staged = StagedRun(
        query=original.request.query,
        kind=original.kind,
        structure=original.form.structure if original.form else original.request.structure,
        sources=original.request.sources,
        until=original.request.until,
        profile=original.profile,
        use=original.use or {},
        depth=original.request.depth,
        set=without_use(original.overrides),
        run_id=fresh_id(runs_dir),
        action="rerun",
        created=datetime.now(UTC),
        resolved_sources=original.request.sources,
        resolved_profile=original.profile,
        writing_options=WritingOptions.model_validate(original.settings.get("write", {})),
        origin=origin,
        token_name=token_name,
        form=original.form,
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


def llm_flags(staged: StagedRun) -> list[str]:
    return llm_overrides(staged.llm)


def llm_overrides(llm: LLMPatch) -> list[str]:
    """The model, the limits, and the thinking levels as `dotted.key=value` overrides."""
    model = [] if llm.model is None else [f"llm.model={toml_value(llm.model)}"]
    limits = llm.model_dump(include=set(LLM_KEYS), exclude_none=True).items()
    levels = llm.reasoning.model_dump(exclude_none=True).items()
    return [
        *model,
        *(f"{LLM_KEYS[name]}={toml_value(value)}" for name, value in limits),
        *(f"llm.reasoning.{step}={toml_value(level)}" for step, level in levels),
    ]


def use_flags(staged: StagedRun) -> list[str]:
    return [flag for block, name in staged.use.items() for flag in ("--use", f"{block}={name}")]


def set_flags(staged: StagedRun) -> list[str]:
    """Writing, research, domains and language, the model and thinking, then the request's own `set`.

    Each later one wins.
    """
    writing = [f"write.{name}={toml_value(value)}" for name, value in staged.writing_flags.items()]
    research = [
        f"{RESEARCH_KEYS[name]}={value}" for name, value in staged.research.model_dump(exclude_none=True).items()
    ]
    domains = [f"{key}={toml_value(value)}" for key, value in staged.domain_flags.items()]
    if staged.search_language is not None:
        domains.append(f"search.language={toml_value(staged.search_language)}")
    return [
        flag for value in [*writing, *research, *domains, *llm_flags(staged), *staged.set] for flag in ("--set", value)
    ]


def depth_flags(staged: StagedRun) -> list[str]:
    return ["--depth", staged.depth] if staged.depth else []


def kind_flags(staged: StagedRun) -> list[str]:
    """`--kind catalog` and the structure as JSON; nothing for a research run."""
    if staged.kind == "research":
        return []
    structure = (
        [] if staged.structure is None else ["--structure", staged.structure.model_dump_json(exclude_unset=True)]
    )
    return ["--kind", staged.kind, *structure]


LIMIT_FLAGS = {"max_depth": "--max-depth", "max_nodes": "--max-nodes", "pages_per_node": "--pages-per-node"}


def limit_flags(staged: StagedRun) -> list[str]:
    raised = staged.limits.model_dump(exclude_none=True).items()
    return [flag for name, value in raised for flag in (LIMIT_FLAGS[name], str(value))]


def build_run_argv(command: list[str], staged: StagedRun, path: Path) -> list[str]:
    argv = [*command, "run", staged.query, "--run-id", staged.run_id, "--sources", staged.resolved_sources]
    if staged.until:
        argv += ["--until", staged.until]
    if staged.profile:
        argv += ["--profile", staged.profile]
    argv += kind_flags(staged)
    return argv + use_flags(staged) + depth_flags(staged) + attach_flags(path) + set_flags(staged)


def build_fork_argv(command: list[str], staged: StagedRun) -> list[str]:
    assert staged.parent is not None
    assert staged.from_stage is not None
    argv = [*command, "fork", staged.parent, "--from", staged.from_stage, "--run-id", staged.run_id]
    if staged.until:
        argv += ["--until", staged.until]
    if staged.profile:
        argv += ["--profile", staged.profile]
    return argv + use_flags(staged) + limit_flags(staged) + set_flags(staged)


def build_rerun_argv(command: list[str], staged: StagedRun, path: Path) -> list[str]:
    argv = [*command, "run", staged.query, "--run-id", staged.run_id, "--sources", staged.resolved_sources]
    if staged.until:
        argv += ["--until", staged.until]
    argv += ["--profile", staged.resolved_profile, *kind_flags(staged), *use_flags(staged), *depth_flags(staged)]
    return argv + attach_flags(path) + [flag for value in staged.set for flag in ("--set", value)]


def origin_flags(staged: StagedRun) -> list[str]:
    token = ["--token-name", staged.token_name] if staged.token_name else []
    form = ["--form", staged.form.model_dump_json(exclude_defaults=True)] if staged.form else []
    return ["--origin", staged.origin, *token, *form]


def build_argv(command: list[str], staged: StagedRun, runs_dir: Path) -> list[str]:
    path = staging_dir(runs_dir, staged.run_id)
    if staged.action == "fork":
        argv = build_fork_argv(command, staged)
    elif staged.action == "rerun":
        argv = build_rerun_argv(command, staged, path)
    else:
        argv = build_run_argv(command, staged, path)
    return argv + origin_flags(staged)

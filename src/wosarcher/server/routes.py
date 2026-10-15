"""`/api/runs`: create, list, show, delete, cancel, fork, rerun, artifacts, and export."""

import os
import shutil
from collections.abc import Mapping
from typing import Annotated, Any, get_args

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import ValidationError

from wosarcher.config import CUSTOM_DEPTH, ConfigError, list_depths, list_entries, own_settings, select_profile
from wosarcher.document import document
from wosarcher.models import (
    CATALOG_STAGES,
    KIND_STEPS,
    STAGES,
    Attachment,
    ExportFormat,
    ForkCreate,
    LLMPatch,
    Origin,
    ReasoningOptions,
    Report,
    ResearchPatch,
    RunCreate,
    RunCreated,
    RunDetail,
    RunFailed,
    RunKind,
    RunNotActive,
    RunRecord,
    RunSummary,
    Stage,
    Structure,
    WritingPatch,
    catalog_writes,
)
from wosarcher.ports import ExportError
from wosarcher.server import staging
from wosarcher.server.errors import RouteError, invalid, not_found
from wosarcher.server.guard import Auth
from wosarcher.server.manager import ActiveRun
from wosarcher.server.staging import OverrideError, StagedRun, StagingError, UnknownRunError
from wosarcher.server.state import ServerState, get_state
from wosarcher.store import attachment_infos
from wosarcher.store import settings as global_settings

router = APIRouter(prefix="/api/runs")
State = Annotated[ServerState, Depends(get_state)]

JSON, JSONL, MARKDOWN = "application/json", "application/x-ndjson", "text/markdown"
ARTIFACTS: dict[str, str] = {
    "request.json": JSON,
    "files.jsonl": JSONL,
    "plan.json": JSON,
    "initial.jsonl": JSONL,
    "hits.jsonl": JSONL,
    "pages.jsonl": JSONL,
    "chunks.jsonl": JSONL,
    "candidates.jsonl": JSONL,
    "scores.jsonl": JSONL,
    "research.json": JSON,
    "context.json": JSON,
    "select.jsonl": JSONL,
    "report.md": MARKDOWN,
    "report.json": JSON,
    "structure.json": JSON,
    "nodes.jsonl": JSONL,
    "records.jsonl": JSONL,
    "catalog.json": JSON,
    "events.jsonl": JSONL,
    "costs.json": JSON,
}
EXPORT_TYPES: dict[ExportFormat, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def origin_of(request: Request) -> tuple[Origin, str | None]:
    """`api` with the token's name for a request with an API token, `cli` on the socket, else `web`."""
    auth: Auth | None = getattr(request.state, "auth", None)
    if auth is not None and auth.method == "token" and auth.token is not None:
        return "api", auth.token.name
    if auth is not None and auth.method == "socket":
        return "cli", None
    return "web", None


def record_of(state: ServerState, run_id: str) -> RunRecord | None:
    path = state.runs_dir / run_id / "request.json"
    return state.store.read_record(run_id) if run_id and not run_id.startswith(".") and path.is_file() else None


def staged_summary(state: ServerState, staged: StagedRun) -> RunSummary:
    running = staged.run_id in state.manager.running
    return RunSummary(
        run_id=staged.run_id,
        query=staged.query,
        kind=staged.kind,
        status="running" if running else "queued",
        created=staged.created,
        parent_run_id=staged.parent,
        version=staged.version,
        fork_from=staged.from_stage,
        profile=staged.resolved_profile,
        sources=staged.resolved_sources,
        until=staged.until,
        depth=staged.depth,
        writing=staged.writing_options if staged.kind == "research" or catalog_writes(staged.structure) else None,
        output=staged.structure.output if staged.kind == "catalog" and staged.structure else None,
        nodes=0 if staged.kind == "catalog" else None,
        queue_position=state.manager.queue_position(staged.run_id),
        model=staged.llm.model or "",
        reasoning=ReasoningOptions.model_validate(staged.llm.reasoning.model_dump(exclude_none=True)),
        modified=bool(staged.use) or staged.llm != LLMPatch(),
        origin=staged.origin,
        token_name=staged.token_name,
        form=staged.form,
        attachments=attachment_infos(staging.staging_dir(state.runs_dir, staged.run_id) / "attachments"),
    )


def ended_summary(state: ServerState, run_id: str) -> RunSummary | None:
    """A run this server remembers as ended without a run directory."""
    ended = state.manager.ended.get(run_id)
    if ended is None:
        return None
    event = ended.event
    update = {
        "status": "failed" if isinstance(event, RunFailed) else "cancelled",
        "error": event.data.error if isinstance(event, RunFailed) else None,
        "end_stage": event.data.stage,
        "queue_position": None,
    }
    return staged_summary(state, ended.staged).model_copy(update=update)


def summary(state: ServerState, run_id: str) -> RunSummary | None:
    """The store's summary, with `queued` or `running` when this server owns the run, or a remembered ended run."""
    active = state.manager.active(run_id)
    record = record_of(state, run_id)
    if record is None:
        return staged_summary(state, active.staged) if active else ended_summary(state, run_id)
    found = state.store.summary(record)
    if active is not None:
        return found.model_copy(update={"status": "running", "duration_s": None})
    return found


def require_finished(state: ServerState, run_id: str) -> RunRecord:
    """The record of a run that is neither queued nor running."""
    if state.manager.active(run_id) is not None or state.store.is_running(run_id):
        raise RouteError(409, "run_active", f"run {run_id} is queued or running")
    record = record_of(state, run_id)
    if record is None:
        raise not_found(run_id)
    return record


def check_use(use: Mapping[str, str]) -> None:
    """Every chosen entry exists in its block; 422 naming `use.<block>` otherwise."""
    if not use:
        return
    try:
        entries = list_entries(os.environ)
    except ConfigError as error:
        raise RouteError(422, "invalid_request", f"use: {error}") from None
    for block, name in use.items():
        if name not in entries[block]:
            listed = ", ".join(entries[block]) or "none"
            raise RouteError(422, "invalid_request", f"use.{block}: unknown entry '{name}'; {block} entries: {listed}")


STRUCTURE_PATHS = (
    ("seed", "seeds"),
    ("leaf type", "leaf_types"),
    ("relation", "relation"),
    ("field", "fields"),
    ("exactly one enum", "fields"),
    ("at most one", "fields"),
    ("at least one required", "fields"),
)


def structure_errors(error: ValidationError) -> list[Any]:
    """The errors with a whole-structure check located at the structure part it names (`structure.seeds`)."""
    found: list[Any] = []
    for item in error.errors():
        loc = tuple(item["loc"])
        message = str(item["msg"]).removeprefix("Value error, ")
        if loc == ("structure",):
            part = next((path for prefix, path in STRUCTURE_PATHS if message.startswith(prefix)), None)
            if part is not None:
                item = {**item, "loc": (*loc, part)}
        found.append(item)
    return found


def kind_stages(kind: str) -> tuple[Stage, ...]:
    return CATALOG_STAGES if kind == "catalog" else STAGES


def check_reasoning(kind: RunKind, llm: LLMPatch) -> None:
    """`llm.reasoning` sets only the steps of the run's kind."""
    for step in llm.reasoning.model_dump(exclude_none=True):
        if step not in KIND_STEPS[kind]:
            detail = f"llm.reasoning: {step} is not a {kind} step; steps: {', '.join(KIND_STEPS[kind])}"
            raise RouteError(422, "invalid_request", detail)


def check_kind(body: RunCreate) -> None:
    """The fields of the other kind, `sources files` for a catalog, `until` outside the kind, two languages."""
    if body.kind == "catalog":
        defaults = {"depth": None, "research": ResearchPatch()}
        given = [name for name, empty in defaults.items() if getattr(body, name) != empty]
        if given:
            raise RouteError(422, "invalid_request", f"{given[0]}: not for catalog runs")
        if body.writing != WritingPatch() and not catalog_writes(body.structure):
            raise RouteError(422, "invalid_request", "writing: not for a catalog whose output is table")
        if body.sources == "files":
            raise RouteError(422, "invalid_request", "sources: a catalog run cannot use files only")
        language = body.structure.language if body.structure else ""
        if language and body.search_language not in (None, language):
            detail = (
                f"search_language: '{body.search_language}' conflicts with structure.language '{language}'; "
                "set one, or make them equal"
            )
            raise RouteError(422, "invalid_request", detail)
    elif body.structure is not None:
        raise RouteError(422, "invalid_request", "structure: only for catalog runs, not research runs")
    check_reasoning(body.kind, body.llm)
    stages = kind_stages(body.kind)
    if body.until is not None and body.until not in stages:
        detail = f"until: {body.until} is not a {body.kind} stage; stages: {', '.join(stages)}"
        raise RouteError(422, "invalid_request", detail)


async def submit(state: ServerState, staged: StagedRun) -> JSONResponse:
    active: ActiveRun = await state.manager.submit(staged)
    status = "running" if active.run_id in state.manager.running else "queued"
    created = RunCreated(run_id=active.run_id, status=status)
    return JSONResponse(created.model_dump(), status_code=201)


@router.post("", status_code=201, response_model=RunCreated)
async def create_run(
    state: State,
    http: Request,
    request: Annotated[str, Form(description="RunCreate as JSON")],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> JSONResponse:
    try:
        body = RunCreate.model_validate_json(request)
    except ValidationError as error:
        raise invalid(structure_errors(error)) from None
    check_kind(body)
    if body.kind == "catalog" and body.structure and not body.structure.language and body.search_language:
        body = body.model_copy(
            update={"structure": body.structure.model_copy(update={"language": body.search_language})}
        )
    try:
        known = [*list_depths(os.environ), CUSTOM_DEPTH]
    except ConfigError as error:
        raise RouteError(422, "invalid_request", f"depth: {error}") from None
    if body.depth is not None and body.depth not in known:
        raise RouteError(422, "invalid_request", f"depth: unknown depth '{body.depth}'; available: {', '.join(known)}")
    check_use(body.use)
    uploads = [Attachment(name=upload.filename or "", data=await upload.read()) for upload in attachments or []]
    defaults = global_settings.load(state.config_dir)
    try:
        own = own_settings(select_profile(body.profile, os.environ), os.environ)
    except ConfigError:
        own = {}
    try:
        default_profile = select_profile(None, os.environ)
    except ConfigError as error:
        raise RouteError(422, "invalid_request", f"profile: {error}") from None
    try:
        origin, token_name = origin_of(http)
        staged = staging.stage_run(state.runs_dir, body, uploads, defaults, default_profile, own, origin, token_name)
    except OverrideError as error:
        raise RouteError(422, "invalid_override", str(error)) from None
    except UnknownRunError:
        assert body.reuse_attachments is not None
        raise not_found(body.reuse_attachments.run_id) from None
    except StagingError as error:
        raise RouteError(422, "invalid_attachment", str(error)) from None
    return await submit(state, staged)


@router.get("")
async def list_runs(state: State) -> list[RunSummary]:
    stored = {run.run_id: run for run in state.store.list_runs(None)}
    active = [*state.manager.running, *(run.run_id for run in state.manager.queued), *state.manager.ended]
    found = {run_id: run for run_id in [*stored, *active] if (run := summary(state, run_id)) is not None}
    return sorted(found.values(), key=lambda run: (run.created, run.run_id), reverse=True)


@router.get("/{run_id}")
async def show_run(state: State, run_id: str) -> RunDetail:
    found = summary(state, run_id)
    if found is None:
        raise not_found(run_id)
    record = record_of(state, run_id)
    if record is None:
        return RunDetail(**found.model_dump())
    costs = state.store.read_costs(run_id)
    last_seq = state.store.read_events(run_id)[-1:]
    return RunDetail(**found.model_dump(), request=record, costs=costs, last_seq=last_seq[0].seq if last_seq else 0)


@router.delete("/{run_id}", status_code=204)
async def delete_run(state: State, run_id: str) -> Response:
    if run_id in state.manager.running or state.store.is_running(run_id):
        raise RouteError(409, "run_active", f"run {run_id} is running; cancel it first")
    if state.manager.queue_position(run_id) is not None:
        await state.manager.cancel(run_id)
        state.manager.forget(run_id)
        return Response(status_code=204)
    if state.manager.forget(run_id):
        return Response(status_code=204)
    if record_of(state, run_id) is None:
        raise not_found(run_id)
    shutil.rmtree(state.runs_dir / run_id)
    return Response(status_code=204)


@router.get("/{run_id}/artifacts/{name}")
async def artifact(state: State, run_id: str, name: str) -> FileResponse:
    if name not in ARTIFACTS or record_of(state, run_id) is None:
        raise RouteError(404, "artifact_not_found", f"no artifact {name} in run {run_id}")
    path = state.runs_dir / run_id / name
    if not path.is_file():
        raise RouteError(404, "artifact_not_found", f"no artifact {name} in run {run_id}")
    return FileResponse(path, media_type=f"{ARTIFACTS[name]}; charset=utf-8")


@router.get("/{run_id}/export")
async def export_run(state: State, run_id: str, format: str | None = None) -> Response:
    if format not in get_args(ExportFormat):
        raise RouteError(422, "invalid_format", f"format must be one of: {', '.join(get_args(ExportFormat))}")
    fmt: ExportFormat = format  # pyright: ignore[reportAssignmentType]  (checked above)
    record = record_of(state, run_id)
    if record is None:
        raise not_found(run_id)
    structure = record.request.structure
    if record.kind == "catalog" and structure is not None and not structure.wants_report:
        raise RouteError(404, "no_report", f"run {run_id} is a catalog with output table; it has no report")
    if not (state.runs_dir / run_id / "report.json").is_file():
        raise RouteError(404, "report_not_found", f"run {run_id} has no report")
    missing = state.exporter.missing(fmt)
    if missing:
        raise RouteError(503, "export_unavailable", f"{fmt.upper()} export needs {' and '.join(missing)} on the server")
    markdown = document(record, state.store.read_artifact(run_id, "report.json", Report))
    try:
        async with state.exports:
            data = await state.exporter.export(markdown, fmt)
    except ExportError as error:
        raise RouteError(500, "export_failed", str(error)) from None
    headers = {"Content-Disposition": f'attachment; filename="{run_id}.{fmt}"'}
    return Response(data, media_type=EXPORT_TYPES[fmt], headers=headers)


@router.post("/{run_id}/cancel")
async def cancel_run(state: State, run_id: str) -> JSONResponse:
    result = await state.manager.cancel(run_id)
    if result is None:
        found = summary(state, run_id)
        if found is None:
            raise not_found(run_id)
        detail = f"run {run_id} is not queued or running (status {found.status})"
        body = RunNotActive(error="run_not_active", detail=detail, run_id=run_id, status=found.status)
        return JSONResponse(body.model_dump(), status_code=409)
    return JSONResponse({"run_id": run_id, "result": result}, status_code=202 if result == "signalled" else 200)


@router.post("/{run_id}/fork", status_code=201, response_model=RunCreated)
async def fork_run(state: State, http: Request, run_id: str, body: ForkCreate) -> JSONResponse:
    parent = require_finished(state, run_id)
    check_fork(state, parent, body)
    missing = state.store.missing_stages(run_id, body.from_stage)
    if missing:
        detail = f"cannot fork {run_id} from {body.from_stage}: stage {missing[0]} is not finished"
        raise RouteError(409, "stage_not_finished", detail)
    check_use(body.use)
    try:
        staged = staging.stage_fork(state.runs_dir, parent, body, *origin_of(http))
    except OverrideError as error:
        raise RouteError(422, "invalid_override", str(error)) from None
    return await submit(state, staged)


CATALOG_FORKS: tuple[Stage, ...] = ("expand", "extract")


def parent_structure(state: ServerState, parent: RunRecord) -> Structure | None:
    path = state.runs_dir / parent.run_id / "structure.json"
    return state.store.read_artifact(parent.run_id, "structure.json", Structure) if path.is_file() else parent.structure


def check_fork(state: ServerState, parent: RunRecord, body: ForkCreate) -> None:
    """The stage is a fork stage of the parent's kind; `writing` and `limits` only where they apply."""
    allowed = CATALOG_FORKS if parent.kind == "catalog" else STAGES
    if body.from_stage not in allowed:
        listed = ", ".join(f"'{stage}'" for stage in allowed)
        detail = f"from: {body.from_stage} is not a fork stage of a {parent.kind} run; allowed: {listed}"
        raise RouteError(422, "invalid_request", detail)
    stages = kind_stages(parent.kind)
    if body.until is not None and body.until not in stages:
        detail = f"until: {body.until} is not a {parent.kind} stage; stages: {', '.join(stages)}"
        raise RouteError(422, "invalid_request", detail)
    check_reasoning(parent.kind, body.llm)
    limits: dict[str, int] = body.limits.model_dump(exclude_none=True)
    if parent.kind == "catalog" and body.writing.model_dump(exclude_none=True):
        raise RouteError(422, "invalid_request", "writing: not for catalog runs")
    if limits and (parent.kind != "catalog" or body.from_stage != "expand"):
        raise RouteError(422, "invalid_request", "limits: only for a catalog fork from expand")
    structure = parent_structure(state, parent)
    if parent.kind != "catalog" or body.from_stage != "expand" or structure is None:
        return
    for name, value in limits.items():
        old = getattr(structure.limits, name)
        if value < old:
            raise RouteError(422, "invalid_request", f"limits.{name}: {value} is below the parent's {old}")
    if not any(value > getattr(structure.limits, name) for name, value in limits.items()):
        raise RouteError(422, "invalid_request", "limits: a fork from expand needs a raised limit")


@router.post("/{run_id}/rerun", status_code=201, response_model=RunCreated)
async def rerun_run(state: State, http: Request, run_id: str) -> JSONResponse:
    if state.manager.queue_position(run_id) is not None:
        raise RouteError(409, "run_queued", f"run {run_id} has not started yet")
    original = record_of(state, run_id)
    if original is None:
        raise not_found(run_id)
    try:
        staged = staging.stage_rerun(state.runs_dir, original, *origin_of(http))
    except OverrideError as error:
        raise RouteError(422, "invalid_override", str(error)) from None
    except StagingError as error:
        raise RouteError(422, "invalid_attachment", str(error)) from None
    return await submit(state, staged)

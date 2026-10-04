"""`/api/runs`: create, list, show, delete, cancel, fork, rerun, and artifacts."""

import os
import shutil
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import ValidationError

from wosarcher.config import CUSTOM_DEPTH, list_depths, select_profile
from wosarcher.models import (
    Attachment,
    ForkCreate,
    RunCreate,
    RunCreated,
    RunDetail,
    RunFailed,
    RunNotActive,
    RunRecord,
    RunSummary,
)
from wosarcher.server import settings as global_settings
from wosarcher.server import staging
from wosarcher.server.errors import RouteError, invalid, not_found
from wosarcher.server.manager import ActiveRun
from wosarcher.server.staging import StagedRun, StagingError
from wosarcher.server.state import ServerState, get_state

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
    "events.jsonl": JSONL,
    "costs.json": JSON,
}


def record_of(state: ServerState, run_id: str) -> RunRecord | None:
    path = state.runs_dir / run_id / "request.json"
    return state.store.read_record(run_id) if run_id and not run_id.startswith(".") and path.is_file() else None


def staged_summary(state: ServerState, staged: StagedRun) -> RunSummary:
    running = staged.run_id in state.manager.running
    return RunSummary(
        run_id=staged.run_id,
        query=staged.query,
        status="running" if running else "queued",
        created=staged.created,
        parent_run_id=staged.parent,
        version=staged.version,
        fork_from=staged.from_stage,
        profile=staged.resolved_profile,
        sources=staged.resolved_sources,
        until=staged.until,
        depth=staged.depth,
        writing=staged.writing_options,
        queue_position=state.manager.queue_position(staged.run_id),
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
    if state.manager.active(run_id) is not None:
        raise RouteError(409, "run_active", f"run {run_id} is queued or running")
    record = record_of(state, run_id)
    if record is None:
        raise not_found(run_id)
    return record


async def submit(state: ServerState, staged: StagedRun) -> JSONResponse:
    active: ActiveRun = await state.manager.submit(staged)
    status = "running" if active.run_id in state.manager.running else "queued"
    created = RunCreated(run_id=active.run_id, status=status)
    return JSONResponse(created.model_dump(), status_code=201)


@router.post("", status_code=201, response_model=RunCreated)
async def create_run(
    state: State,
    request: Annotated[str, Form(description="RunCreate as JSON")],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> JSONResponse:
    try:
        body = RunCreate.model_validate_json(request)
    except ValidationError as error:
        raise invalid(error.errors()) from None
    known = [*list_depths(), CUSTOM_DEPTH]
    if body.depth is not None and body.depth not in known:
        raise RouteError(422, "invalid_request", f"depth: unknown depth '{body.depth}'; available: {', '.join(known)}")
    uploads = [Attachment(name=upload.filename or "", data=await upload.read()) for upload in attachments or []]
    defaults = global_settings.load(state.config_dir)
    try:
        staged = staging.stage_run(state.runs_dir, body, uploads, defaults, select_profile(None, os.environ))
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
    if run_id in state.manager.running:
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
async def fork_run(state: State, run_id: str, body: ForkCreate) -> JSONResponse:
    parent = require_finished(state, run_id)
    missing = state.store.missing_stages(run_id, body.from_stage)
    if missing:
        detail = f"cannot fork {run_id} from {body.from_stage}: stage {missing[0]} is not finished"
        raise RouteError(409, "stage_not_finished", detail)
    return await submit(state, staging.stage_fork(state.runs_dir, parent, body))


@router.post("/{run_id}/rerun", status_code=201, response_model=RunCreated)
async def rerun_run(state: State, run_id: str) -> JSONResponse:
    if state.manager.queue_position(run_id) is not None:
        raise RouteError(409, "run_queued", f"run {run_id} has not started yet")
    original = record_of(state, run_id)
    if original is None:
        raise not_found(run_id)
    try:
        staged = staging.stage_rerun(state.runs_dir, original)
    except StagingError as error:
        raise RouteError(422, "invalid_attachment", str(error)) from None
    return await submit(state, staged)

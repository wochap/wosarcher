"""`POST /api/catalog/draft`: derive a catalog structure from a brief without creating a run."""

import os
from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import ValidationError

from wosarcher.config import BLOCKS, ConfigError, resolve_run
from wosarcher.http import UsageLedger
from wosarcher.models import Attachment, DraftCreate, Structure
from wosarcher.server.errors import RouteError, invalid
from wosarcher.server.routes import check_use
from wosarcher.server.staging import llm_overrides
from wosarcher.server.state import ServerState, get_state
from wosarcher.stages.draft import DraftFailedError, draft_structure
from wosarcher.stages.load import load, outline

router = APIRouter(prefix="/api/catalog")
State = Annotated[ServerState, Depends(get_state)]


@router.post("/draft")
async def draft(
    state: State,
    request: Annotated[str, Form(description="DraftCreate as JSON")],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> Structure:
    try:
        body = DraftCreate.model_validate_json(request)
    except ValidationError as error:
        raise invalid(error.errors()) from None
    check_use(body.use)
    overrides = [*llm_overrides(body.llm), *(f"use.{block}={name}" for block, name in body.use.items())]
    try:
        settings = resolve_run(body.profile, overrides, os.environ).settings
    except (ConfigError, ValueError) as error:
        raise RouteError(422, "invalid_request", f"profile: {error}") from None
    uploads = [Attachment(name=upload.filename or "", data=await upload.read()) for upload in attachments or []]
    outlines = [outline(page) for page in load(uploads).pages]
    ledger = UsageLedger({getattr(settings, block).provider: getattr(settings, block).prices for block in BLOCKS})
    try:
        async with httpx.AsyncClient() as http:
            llm = state.draft_llm(settings, http, ledger)
            return await draft_structure(
                body.brief,
                outlines,
                llm,
                today=date.today().isoformat(),
                catalog=settings.catalog,
                effort=settings.llm.reasoning.draft,
            )
    except DraftFailedError as error:
        raise RouteError(502, "draft_failed", error.reason) from None
    except ValueError as error:
        raise RouteError(502, "draft_failed", str(error)) from None

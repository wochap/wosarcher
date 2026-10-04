"""`/api/settings`, `/api/profiles`, `/api/depths`, `/api/providers/health`, and `/api/providers/health/check`."""

import asyncio
import os
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from wosarcher.config import (
    RESEARCH_KEYS,
    ConfigError,
    Settings,
    depth_values,
    list_depths,
    list_profiles,
    profile_description,
    read_depth,
    resolve,
    select_profile,
)
from wosarcher.doctor import BLOCKS
from wosarcher.models import (
    DepthInfo,
    DepthValues,
    DoctorReport,
    HealthCheckRequest,
    HealthReport,
    ProfileInfo,
    ServerSettings,
)
from wosarcher.server import settings as global_settings
from wosarcher.server.errors import RouteError
from wosarcher.server.state import ServerState, get_state

router = APIRouter(prefix="/api")
State = Annotated[ServerState, Depends(get_state)]

DOCTOR_TIMEOUT = 60.0


@router.get("/settings")
async def get_settings(state: State) -> ServerSettings:
    return global_settings.load(state.config_dir)


@router.put("/settings")
async def put_settings(state: State, body: ServerSettings) -> ServerSettings:
    global_settings.save(state.config_dir, body)
    return body


def profile_info(name: str, source: str, active: str) -> ProfileInfo:
    info = ProfileInfo(
        name=name,
        source="builtin" if source == "built-in" else "user",
        active=name == active,
        description=profile_description(name, os.environ),
    )
    try:
        settings = resolve(name, [], os.environ)
    except ConfigError:
        return info
    limits = {
        "context_window": settings.llm.context_window,
        "prompt_reserve_tokens": settings.select.prompt_reserve_tokens,
        "max_output_tokens": settings.llm.max_output_tokens,
    }
    return info.model_copy(update=limits)


@router.get("/profiles")
async def profiles() -> list[ProfileInfo]:
    active = select_profile(None, os.environ)
    return [profile_info(name, source, active) for name, (_, source) in list_profiles(os.environ).items()]


def depth_info(name: str) -> DepthInfo:
    """The preset's values, the built-in default where it sets none; `words` stays None then."""
    _, description, data = read_depth(name)
    values = depth_values(data)
    defaults = Settings()
    research = {
        field: values.get(key, getattr(getattr(defaults, key.split(".")[0]), key.split(".")[1]))
        for field, key in RESEARCH_KEYS.items()
    }
    per_round = values.get("research.queries_per_round", defaults.research.queries_per_round)
    depth = DepthValues(**research, queries_per_round=per_round, words=values.get("write.words"))
    return DepthInfo(name=name, description=description, values=depth)


@router.get("/depths")
async def depths() -> list[DepthInfo]:
    return [depth_info(name) for name in list_depths()]


async def run_doctor(command: list[str], profile: str, chosen: list[str]) -> DoctorReport:
    """`<command> doctor --json`; exit code 1 (a failed probe) still prints a report."""
    argv = [*command, "doctor", "--json", "--profile", profile, *(f"--block={name}" for name in chosen)]
    process = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), DOCTOR_TIMEOUT)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RouteError(502, "health_unavailable", f"doctor did not finish within {DOCTOR_TIMEOUT:.0f} s") from None
    try:
        return DoctorReport.model_validate_json(stdout)
    except ValidationError:
        reason = stderr.decode("utf-8", errors="replace").strip() or "unreadable output"
        raise RouteError(502, "health_unavailable", f"doctor failed: {reason}") from None


def profile_settings(profile: str | None) -> tuple[str, Settings]:
    name = select_profile(profile, os.environ)
    try:
        return name, resolve(name, [], os.environ)
    except ConfigError as error:
        raise RouteError(400, "invalid_profile", str(error)) from None


@router.get("/providers/health")
async def providers_health(state: State, profile: str | None = None) -> HealthReport:
    """The configured providers with the last stored check of each; sends no probe."""
    name, settings = profile_settings(profile)
    return state.health.report(name, settings)


@router.post("/providers/health/check")
async def check_health(
    state: State, body: HealthCheckRequest | None = None, profile: str | None = None
) -> HealthReport:
    """Probe the chosen blocks (every block when none), store the results, and return the merged report."""
    name, settings = profile_settings(profile)
    chosen = body.blocks if body else []
    unknown = [block for block in chosen if block not in BLOCKS]
    if unknown:
        raise RouteError(400, "invalid_block", f"unknown block {', '.join(unknown)}; choose from {', '.join(BLOCKS)}")
    async with state.health.lock:
        doctor = await run_doctor(state.command, name, chosen)
        state.health.store(name, settings, doctor, datetime.now(UTC))
    return state.health.report(name, settings)

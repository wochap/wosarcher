"""`/api/settings`, `/api/profiles`, and `/api/providers/health`."""

import asyncio
import os
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from wosarcher.config import list_profiles, profile_description, select_profile
from wosarcher.models import DoctorReport, HealthReport, ProfileInfo, ProviderCheck, ProviderHealth, ServerSettings
from wosarcher.server import settings as global_settings
from wosarcher.server.errors import RouteError
from wosarcher.server.state import ServerState, get_state

router = APIRouter(prefix="/api")
State = Annotated[ServerState, Depends(get_state)]

DOCTOR_TIMEOUT = 60.0
SLOW_MS = 1000


@router.get("/settings")
async def get_settings(state: State) -> ServerSettings:
    return global_settings.load(state.config_dir)


@router.put("/settings")
async def put_settings(state: State, body: ServerSettings) -> ServerSettings:
    global_settings.save(state.config_dir, body)
    return body


@router.get("/profiles")
async def profiles() -> list[ProfileInfo]:
    active = select_profile(None, os.environ)
    return [
        ProfileInfo(
            name=name,
            source="builtin" if source == "built-in" else "user",
            active=name == active,
            description=profile_description(name, os.environ),
        )
        for name, (_, source) in list_profiles(os.environ).items()
    ]


def provider_check(row: ProviderHealth) -> ProviderCheck:
    if row.status == "failed":
        status, detail = "down", row.error or "probe failed"
    elif row.status == "built-in":
        status, detail = "skipped", "built in, no endpoint"
    elif row.unload == "no":
        status, detail = "degraded", "model cannot be unloaded"
    elif row.latency_ms is not None and row.latency_ms > SLOW_MS:
        status, detail = "degraded", "slow response"
    else:
        status, detail = "ok", row.note or ""
    return ProviderCheck(
        role=row.block,
        provider=row.provider,
        url=row.base_url,
        model=row.model,
        device=row.device,
        release=row.release,
        status=status,
        latency_ms=row.latency_ms,
        detail=detail,
    )


def health_report(profile: str, doctor: DoctorReport) -> HealthReport:
    checks = [provider_check(row) for row in doctor.providers]
    return HealthReport(profile=profile, gpu_policy=doctor.gpu_policy, checks=checks, warnings=list(doctor.warnings))


async def run_doctor(command: list[str], profile: str | None) -> DoctorReport:
    """`<command> doctor --json`; exit code 1 (a failed probe) still prints a report."""
    argv = [*command, "doctor", "--json", *(["--profile", profile] if profile else [])]
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


@router.get("/providers/health")
async def providers_health(state: State, profile: str | None = None) -> HealthReport:
    doctor = await run_doctor(state.command, profile)
    return health_report(profile or select_profile(None, os.environ), doctor)

"""`/api/settings`, `/api/profiles`, `/api/providers` (and `/check`), `/api/models`, and `/api/depths`.

Profiles and depth presets are also saved and deleted here (`store.presets`).
"""

import asyncio
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from wosarcher.adapters.llm import ChatLLM
from wosarcher.config import (
    BLOCKS,
    RESEARCH_KEYS,
    ConfigError,
    Entry,
    Settings,
    depth_values,
    entry_block,
    entry_settings,
    env_layer,
    list_depths,
    list_entries,
    list_profiles,
    own_settings,
    read_depth,
    read_entry,
    read_profile,
    redact,
    resolve,
    resolve_run,
    select_profile,
)
from wosarcher.http import ProviderClient, UsageLedger
from wosarcher.models import (
    DepthInfo,
    DepthSave,
    DepthUpdate,
    DepthValues,
    DoctorReport,
    ModelInfo,
    ModelList,
    ProfileInfo,
    ProfileSave,
    ProfileUpdate,
    ProviderEntryInfo,
    ProvidersCheck,
    ProvidersReport,
    ReasoningPatch,
    ServerSettings,
    SlotState,
)
from wosarcher.server.errors import RouteError
from wosarcher.server.state import ServerState, get_state
from wosarcher.store import presets
from wosarcher.store import settings as global_settings

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


@router.get("/slots")
async def get_slots(state: State) -> SlotState:
    return state.manager.slot_state()


def active_profile() -> str | None:
    try:
        return select_profile(None, os.environ)
    except ConfigError:
        return None


def profile_use(use: Mapping[str, str], entries: Mapping[str, Mapping[str, Entry]]) -> dict[str, str | None]:
    """The entry each block resolves to, or None where the choice is missing or names no entry."""
    _, env_use = env_layer(os.environ)
    chosen: dict[str, str | None] = {}
    for block in BLOCKS:
        name = env_use.get(block) or use.get(block)
        if name is None and len(entries[block]) == 1:
            name = next(iter(entries[block]))
        chosen[block] = name if name in entries[block] else None
    return chosen


def profile_info(name: str, active: str | None, managed: set[str]) -> ProfileInfo:
    info = ProfileInfo(name=name, active=name == active, managed=name in managed)
    try:
        profile = read_profile(name, os.environ)
        model = profile.data.get("llm", {}).get("model")
        info = info.model_copy(
            update={
                "description": profile.description,
                "use": profile_use(profile.use, list_entries(os.environ)),
                "model": model if isinstance(model, str) else None,
                "models": [model_info(model, profile.models[model]) for model in profile.models],
            }
        )
        settings = resolve(name, [], os.environ)
        own = own_settings(name, os.environ)
    except ConfigError as error:
        return info.model_copy(update={"error": str(error)})
    values = {
        "context_tokens": settings.select.max_context_tokens,
        "prompt_reserve_tokens": settings.select.prompt_reserve_tokens,
        "allow_domains": settings.search.allow_domains if "search.allow_domains" in own else None,
        "block_domains": settings.search.block_domains if "search.block_domains" in own else None,
        "settings": redact(settings),
    }
    return info.model_copy(update=values)


@router.get("/profiles")
async def profiles() -> list[ProfileInfo]:
    active = active_profile()
    managed = presets.managed_names(os.environ)[0]
    return [profile_info(name, active, managed) for name in list_profiles(os.environ)]


PRESET_STATUS = {
    "invalid_name": 422,
    "invalid_request": 422,
    "name_taken": 409,
    "managed": 409,
    "builtin": 409,
    "active_profile": 409,
    "profile_not_found": 404,
    "depth_not_found": 404,
}


def saving(action: Callable[[], None]) -> None:
    """Run a preset write, its errors as the saved-presets statuses."""
    try:
        action()
    except presets.PresetError as error:
        raise RouteError(PRESET_STATUS[error.code], error.code, error.detail) from None
    except ConfigError as error:
        raise RouteError(422, "invalid_request", str(error)) from None


def saved_profile(name: str) -> ProfileInfo:
    return profile_info(name, active_profile(), presets.managed_names(os.environ)[0])


@router.post("/profiles", status_code=201)
async def save_profile(body: ProfileSave) -> ProfileInfo:
    saving(lambda: presets.save_profile(body.name, body.from_profile, body, os.environ))
    return saved_profile(body.name)


@router.patch("/profiles/{name}")
async def update_profile(name: str, body: ProfileUpdate) -> ProfileInfo:
    saving(lambda: presets.update_profile(name, body, os.environ))
    return saved_profile(name)


@router.delete("/profiles/{name}", status_code=204)
async def delete_profile(name: str) -> Response:
    saving(lambda: presets.delete_profile(name, os.environ))
    return Response(status_code=204)


def model_info(model: str, values: Mapping[str, Any]) -> ModelInfo:
    return ModelInfo(
        id=model,
        context_window=values.get("context_window"),
        max_output_tokens=values.get("max_output_tokens"),
        reasoning=ReasoningPatch.model_validate(values.get("reasoning", {})),
        gap_context_tokens=values.get("gap_context_tokens"),
    )


def model_infos(default: str, models: Mapping[str, Mapping[str, Any]]) -> list[ModelInfo]:
    """The listed models, the default first (also when it is not listed)."""
    ids = [default] if default else []
    ids += [model for model in models if model != default]
    return [model_info(model, models.get(model, {})) for model in ids]


def entry_info(entry: Entry) -> ProviderEntryInfo:
    """The entry's public fields; an entry that does not load is listed with its error."""
    info = ProviderEntryInfo(block=entry.block, name=entry.name, source=entry.source)  # pyright: ignore[reportArgumentType]
    try:
        data = read_entry(entry)
        cfg = entry_block(data)
        models = model_infos(cfg.model, data.models) if entry.block == "llm" else []
    except (ConfigError, ValidationError) as error:
        return info.model_copy(update={"error": str(error)})
    fields = {
        "description": data.description,
        "provider": cfg.provider,
        "url": cfg.base_url,
        "model": cfg.model,
        "device": cfg.device,
        "release": cfg.release,
        "models": models,
    }
    return info.model_copy(update=fields)


def all_entries() -> list[ProviderEntryInfo]:
    try:
        entries = list_entries(os.environ)
    except ConfigError as error:
        raise RouteError(500, "invalid_providers", str(error)) from None
    return [entry_info(entry) for block in BLOCKS for entry in entries[block].values()]


def providers_report(state: ServerState, entries: list[ProviderEntryInfo]) -> ProvidersReport:
    profile = active_profile()
    try:
        policy = resolve(profile, [], os.environ).run.gpu_policy if profile else "shared"
    except ConfigError:
        policy = "shared"
    merged = [state.health.merge(info) for info in entries]
    return ProvidersReport(profile=profile, gpu_policy=policy, entries=merged, warnings=state.health.warnings)


@router.get("/providers")
async def providers(state: State) -> ProvidersReport:
    """Every entry by block with its stored health; sends no probe."""
    return providers_report(state, all_entries())


async def run_doctor(command: list[str], profile: str | None, chosen: list[str]) -> DoctorReport:
    """`<command> doctor --json --entry ...`; exit code 1 (a failed probe) still prints a report."""
    selected = ["--profile", profile] if profile else []
    entries = [f"--entry={name}" for name in chosen] if chosen else ["--all-entries"]
    argv = [*command, "doctor", "--json", *selected, *entries]
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


def checked_entries(names: list[str], entries: list[ProviderEntryInfo]) -> list[str]:
    """`<block>/<name>` as the doctor's `BLOCK=NAME`; 400 naming an unknown block or entry."""
    known = {(info.block, info.name) for info in entries}
    chosen: list[str] = []
    for name in names:
        block, _, entry = name.partition("/")
        if block not in BLOCKS:
            raise RouteError(
                400, "invalid_entry", f"unknown block '{block}' in {name}; choose from {', '.join(BLOCKS)}"
            )
        if (block, entry) not in known:
            raise RouteError(400, "invalid_entry", f"unknown entry {name}")
        chosen.append(f"{block}={entry}")
    return chosen


@router.post("/providers/check")
async def check_providers(state: State, body: ProvidersCheck | None = None) -> ProvidersReport:
    """Probe the listed entries (every entry when none), store the results, and return the merged list."""
    entries = all_entries()
    chosen = checked_entries(body.entries if body else [], entries)
    async with state.health.lock:
        doctor = await run_doctor(state.command, active_profile(), chosen)
        state.health.store(entries, doctor, datetime.now(UTC))
    return providers_report(state, entries)


@router.get("/models")
async def models(llm: str | None = None) -> ModelList:
    """What the llm entry's endpoint lists at `GET /models`; empty on any failure."""
    try:
        name = llm or resolve_run(None, [], os.environ).use["llm"]
    except ConfigError:
        return ModelList()
    try:
        settings = entry_settings("llm", name, os.environ)
    except ConfigError as error:
        if llm is not None and name not in list_entries(os.environ)["llm"]:
            raise RouteError(400, "invalid_entry", str(error)) from None
        return ModelList()
    ledger = UsageLedger({})
    async with httpx.AsyncClient() as http:
        chat = ChatLLM(settings.llm, ProviderClient(settings.llm.provider, settings.llm, http, ledger), ledger, "plan")
        return ModelList(models=await chat.models())


def depth_info(name: str, managed: set[str]) -> DepthInfo:
    """The preset's values, the built-in default where it sets none; `words` stays None then."""
    depth, description, data = read_depth(name, os.environ)
    values = depth_values(data)
    defaults = Settings()
    research = {
        field: values.get(key, getattr(getattr(defaults, key.split(".")[0]), key.split(".")[1]))
        for field, key in RESEARCH_KEYS.items()
    }
    found = DepthValues(**research, words=values.get("write.words"))
    is_managed = depth.source == "user" and name in managed
    return DepthInfo(name=name, description=description, source=depth.source, managed=is_managed, values=found)


@router.get("/depths")
async def depths() -> list[DepthInfo]:
    try:
        managed = presets.managed_names(os.environ)[1]
        return [depth_info(name, managed) for name in list_depths(os.environ)]
    except ConfigError as error:
        raise RouteError(500, "invalid_depths", str(error)) from None


def saved_depth(name: str) -> DepthInfo:
    return depth_info(name, presets.managed_names(os.environ)[1])


@router.post("/depths", status_code=201)
async def save_depth(body: DepthSave) -> DepthInfo:
    saving(lambda: presets.save_depth(body.name, body, os.environ))
    return saved_depth(body.name)


@router.put("/depths/{name}")
async def replace_depth(name: str, body: DepthUpdate) -> DepthInfo:
    saving(lambda: presets.replace_depth(name, body, os.environ))
    return saved_depth(name)


@router.delete("/depths/{name}", status_code=204)
async def delete_depth(name: str) -> Response:
    saving(lambda: presets.delete_depth(name, os.environ))
    return Response(status_code=204)

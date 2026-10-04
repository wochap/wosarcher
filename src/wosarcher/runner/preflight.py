"""`run.preflight`: probe the providers of the stages a run will use before the first one starts."""

from collections.abc import Mapping, Sequence

from wosarcher.config import Settings
from wosarcher.doctor import BUILT_IN, blocks, check, is_local
from wosarcher.models import Stage
from wosarcher.ports import Managed
from wosarcher.runner.devices import STAGE_BLOCK


async def preflight(
    settings: Settings, managed: Mapping[str, Managed], runnable: Sequence[Stage]
) -> tuple[Stage, str] | None:
    """The first stage using a down block and the error, or None when every probed block answers."""
    mode = settings.run.preflight
    if mode == "off":
        return None
    configured = blocks(settings)
    first_stage: dict[str, Stage] = {}
    for stage in runnable:
        name = STAGE_BLOCK.get(stage)
        if name and name not in first_stage:
            first_stage[name] = stage
    chosen = [
        name
        for name in first_stage
        if name in managed
        and configured[name].provider not in BUILT_IN
        and (mode == "all" or not is_local(configured[name]))
    ]
    if not chosen:
        return None
    report = await check(settings, managed, chosen)
    for row in report.providers:
        if row.status == "failed":
            return first_stage[row.block], f"preflight: {row.block} unreachable: {row.error or 'probe failed'}"
    return None

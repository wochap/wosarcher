"""Which stages use a GPU device, and when the exclusive policy releases a model."""

from collections.abc import Sequence

from wosarcher.config import Provider, Settings
from wosarcher.models import Stage

GPU_BLOCK: dict[Stage, str] = {"plan": "llm", "prefilter": "prefilter", "score": "score", "write": "llm"}
STAGE_BLOCK: dict[Stage, str] = {**GPU_BLOCK, "search": "search", "fetch": "fetch"}


def block_of(stage: Stage, settings: Settings) -> Provider | None:
    name = STAGE_BLOCK.get(stage)
    return getattr(settings, name) if name else None


def gpu_device(stage: Stage, settings: Settings) -> str | None:
    """The device label of a GPU stage's block; None when the stage uses no device."""
    return getattr(settings, GPU_BLOCK[stage]).device if stage in GPU_BLOCK else None


def stage_provider(stage: Stage, settings: Settings) -> str:
    block = block_of(stage, settings)
    if block is None:
        return "built-in"
    return f"{block.provider}:{block.model}" if block.model else block.provider


def next_gpu_stage(remaining: Sequence[Stage], settings: Settings) -> Stage | None:
    return next((stage for stage in remaining if gpu_device(stage, settings)), None)


def needs_release(done: Stage, remaining: Sequence[Stage], settings: Settings) -> bool:
    """Exclusive policy: release when the next GPU stage that runs shares the device but not the block."""
    device = gpu_device(done, settings)
    following = next_gpu_stage(remaining, settings)
    if settings.run.gpu_policy != "exclusive" or device is None or following is None:
        return False
    return gpu_device(following, settings) == device and GPU_BLOCK[following] != GPU_BLOCK[done]

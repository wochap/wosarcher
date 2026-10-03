"""Provider health: probe every configured block, check unload support, warn about exclusive GPU use."""

import asyncio
from collections import defaultdict
from collections.abc import Mapping

from wosarcher.config import Provider, Settings
from wosarcher.models import DoctorReport, ProviderHealth
from wosarcher.ports import Managed

BLOCKS = ("search", "fetch", "prefilter", "score", "llm")
BUILT_IN = {"bm25", "passthrough", "none"}


def blocks(settings: Settings) -> dict[str, Provider]:
    return {name: getattr(settings, name) for name in BLOCKS}


def exclusive_warnings(settings: Settings) -> list[str]:
    """Blocks that share a device with another block but cannot unload, under `gpu_policy = "exclusive"`."""
    if settings.run.gpu_policy != "exclusive":
        return []
    by_device: dict[str, list[str]] = defaultdict(list)
    for name, cfg in blocks(settings).items():
        if cfg.device and cfg.provider not in BUILT_IN:
            by_device[cfg.device].append(name)
    return [
        f'{name} shares device {device} under exclusive GPU policy but has release = "none"; '
        f'set release to "llama-swap" or "ollama"'
        for device, names in by_device.items()
        if len(names) > 1
        for name in names
        if blocks(settings)[name].release == "none"
    ]


async def check(settings: Settings, managed: Mapping[str, Managed]) -> DoctorReport:
    """One row per block, in block order; remote blocks are probed concurrently."""
    configured = blocks(settings)
    probed = dict(zip(managed, await asyncio.gather(*(adapter.probe() for adapter in managed.values())), strict=True))
    rows: list[ProviderHealth] = []
    warnings: list[str] = []
    for name, cfg in configured.items():
        row = probed.get(name)
        if row is None:
            row = ProviderHealth(block=name, provider=cfg.provider, status="built-in")
        elif row.unload == "no" and cfg.release != "none":
            warnings.append(f"{name} cannot unload: {row.base_url} does not answer like {cfg.release}")
        if name == "llm" and row.context_window is not None and row.context_window < settings.llm.context_window:
            size, window = row.context_window, settings.llm.context_window
            warnings.append(
                f"llm server context is {size} tokens, below llm.context_window = {window}; "
                f"start the server with a larger context (llama-server -c {window}) or lower llm.context_window"
            )
        rows.append(row)
    return DoctorReport(providers=tuple(rows), warnings=tuple(warnings + exclusive_warnings(settings)))

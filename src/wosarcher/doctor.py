"""Provider health: probe every configured block, check unload support, warn about exclusive GPU use."""

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence

from wosarcher.config import Provider, Settings
from wosarcher.models import DoctorReport, ProviderHealth
from wosarcher.ports import Managed

BLOCKS = ("search", "fetch", "prefilter", "score", "llm")
BUILT_IN = {"bm25", "passthrough", "none"}


def blocks(settings: Settings) -> dict[str, Provider]:
    return {name: getattr(settings, name) for name in BLOCKS}


def exclusive_warnings(settings: Settings, chosen: Sequence[str] | None = None) -> list[str]:
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
        if blocks(settings)[name].release == "none" and (chosen is None or name in chosen)
    ]


def is_local(cfg: Provider) -> bool:
    """A self-hosted model server: it can unload, or it runs on a labelled device."""
    return cfg.release != "none" or cfg.device is not None


async def probe_all(
    settings: Settings, managed: Mapping[str, Managed], warnings: list[str]
) -> dict[str, ProviderHealth]:
    """Cloud blocks concurrently; local blocks one at a time beside them, in block order."""
    configured = blocks(settings)
    local = [name for name in managed if is_local(configured[name])]
    cloud = [name for name in managed if name not in local]

    async def chain() -> dict[str, ProviderHealth]:
        rows: dict[str, ProviderHealth] = {}
        for index, name in enumerate(local):
            rows[name] = await managed[name].probe()
            last = index == len(local) - 1
            if settings.run.gpu_policy == "exclusive" and rows[name].unload == "yes" and not last:
                try:
                    await managed[name].release()
                except Exception as error:
                    warnings.append(f"{name} release failed: {error}")
        return rows

    cloud_rows, local_rows = await asyncio.gather(asyncio.gather(*(managed[name].probe() for name in cloud)), chain())
    return {**dict(zip(cloud, cloud_rows, strict=True)), **local_rows}


async def check(
    settings: Settings, managed: Mapping[str, Managed], chosen: Sequence[str] | None = None
) -> DoctorReport:
    """One row per chosen block (every block when `chosen` is None), in block order."""
    configured = {name: cfg for name, cfg in blocks(settings).items() if chosen is None or name in chosen}
    warnings: list[str] = []
    probed = await probe_all(settings, {name: managed[name] for name in managed if name in configured}, warnings)
    rows: list[ProviderHealth] = []
    for name, cfg in configured.items():
        row = probed.get(name)
        if row is None:
            row = ProviderHealth(block=name, provider=cfg.provider, status="built-in")
        elif row.unload == "no" and cfg.release != "none":
            warnings.append(f"{name} cannot unload: {row.base_url} does not answer like {cfg.release}")
        row = row.model_copy(update={"release": cfg.release})
        if name == "llm" and row.context_window is not None and row.context_window < settings.llm.context_window:
            size, window = row.context_window, settings.llm.context_window
            warnings.append(
                f"llm server context is {size} tokens, below llm.context_window = {window}; "
                f"start the server with a larger context (llama-server -c {window}) or lower llm.context_window"
            )
        rows.append(row)
    return DoctorReport(
        gpu_policy=settings.run.gpu_policy,
        providers=tuple(rows),
        warnings=tuple(warnings + exclusive_warnings(settings, chosen)),
    )

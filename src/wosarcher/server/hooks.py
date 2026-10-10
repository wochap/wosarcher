"""Firing `[[on_finish]]` hooks when a server run ends.

`hooks.toml` is read and each hook's secrets resolved on every run end, in a
thread, so edits and rotated secrets apply without a restart and the event
loop never blocks. Every failure is logged and never raised.
"""

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from wosarcher import build
from wosarcher.config import ConfigError, HookEntry, load_hooks, resolve_hook
from wosarcher.models import RunFinished
from wosarcher.ports import Hook, HookError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HookLoader:
    load: Callable[[], list[HookEntry]]
    """Every entry of `hooks.toml`; raises `ConfigError` when the file is invalid."""
    build: Callable[[HookEntry], Hook]
    """The hook for a resolved entry."""


def default_loader(env: Mapping[str, str]) -> HookLoader:
    return HookLoader(load=lambda: load_hooks(env), build=lambda entry: build.hooks([entry], env)[0][1])


def describe(error: BaseException) -> str:
    """Why a hook failed, without headers, secrets, the body, or the URL (httpx messages may carry it)."""
    if isinstance(error, HookError | ConfigError):
        return str(error)
    if isinstance(error, TimeoutError):
        return "timed out"
    if isinstance(error, OSError) and error.strerror:
        return f"{type(error).__name__}: {error.strerror}"
    return type(error).__name__


def resolve_and_build(loader: HookLoader, index: int, entry: HookEntry) -> Hook:
    return loader.build(resolve_hook(index, entry))


async def fire_hooks(loader: HookLoader, finished: RunFinished) -> None:
    try:
        entries = await asyncio.to_thread(loader.load)
    except ConfigError as error:
        log.warning("hooks.toml is invalid; no hooks fired for run %s: %s", finished.run_id, error)
        return
    for index, entry in enumerate(entries, 1):
        if finished.status not in entry.status:
            continue
        try:
            hook = await asyncio.to_thread(resolve_and_build, loader, index, entry)
            await asyncio.wait_for(hook.fire(finished), entry.timeout)
        except Exception as error:
            log.warning("hook %d (%s) failed for run %s: %s", index, entry.kind, finished.run_id, describe(error))

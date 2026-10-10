"""Command hook: runs an argv list without a shell; the run's values arrive as `WA_HOOK_*` variables."""

import asyncio
from collections.abc import Mapping

from wosarcher.config import ENV_PREFIX, HookEntry
from wosarcher.models import RunFinished
from wosarcher.ports import HookError

KEPT_ENV = ("WOSARCHER_PROFILE", "WOSARCHER_SOCKET", "WOSARCHER_URL")
STDERR_TAIL = 200


def hook_env(env: Mapping[str, str], finished: RunFinished) -> dict[str, str]:
    """`env` without `WOSARCHER_*` (provider keys, overrides) except `KEPT_ENV`, plus the run's values."""
    kept = {name: value for name, value in env.items() if not name.startswith(ENV_PREFIX) or name in KEPT_ENV}
    return kept | {
        "WA_HOOK_RUN_ID": finished.run_id,
        "WA_HOOK_STATUS": finished.status,
        "WA_HOOK_QUERY": finished.query,
        "WA_HOOK_RUN_DIR": finished.run_dir or "",
        "WA_HOOK_REPORT": finished.report_path or "",
        "WA_HOOK_PAYLOAD": finished.model_dump_json(),
    }


class CommandHook:
    def __init__(self, entry: HookEntry, env: Mapping[str, str]) -> None:
        assert entry.command is not None
        self.argv = entry.command
        self.env = env

    async def fire(self, finished: RunFinished) -> None:
        process = await asyncio.create_subprocess_exec(
            *self.argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=hook_env(self.env, finished),
        )
        try:
            _, stderr = await process.communicate()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        if process.returncode != 0:
            tail = stderr.decode("utf-8", errors="replace").strip()[-STDERR_TAIL:]
            raise HookError(f"exit code {process.returncode}" + (f": {tail}" if tail else ""))

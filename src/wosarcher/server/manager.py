"""The server's run queue: one subprocess per run, first in, first out, at most `max_concurrent_runs` at once.

Staged runs wait in `queued` in staging order. A tick every 0.25 s reads the
limit from the global settings and starts the oldest staged runs while fewer
than the limit execute. Each started run gets one coroutine that polls its
tail, waits for exit, and finalises the log when the process ended without a
terminal event. Runs the server did not start are not queued, counted, or
cancelled here; their status comes from their run lock (`RunStore.is_running`).
"""

import asyncio
import logging
import signal
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from wosarcher.models import (
    Event,
    RunCancelled,
    RunCancelledData,
    RunFailed,
    RunFailedData,
    RunQueued,
    RunQueuedData,
    SlotEntry,
    SlotHolder,
    SlotState,
)
from wosarcher.server import staging
from wosarcher.server.staging import StagedRun
from wosarcher.server.tail import RunTail
from wosarcher.store import RunStore
from wosarcher.store import settings as global_settings

log = logging.getLogger(__name__)

POLL_SECONDS = 0.1
TICK_SECONDS = 0.25
GRACE_SECONDS = 10.0
STDERR_LINES = 20
STDERR_MAX_CHARS = 4000
STDERR_CHUNK = 65536
ENDED_LIMIT = 100


@dataclass
class ActiveRun:
    staged: StagedRun
    tail: RunTail
    started: datetime | None = None
    argv: list[str] = field(default_factory=list[str])
    process: asyncio.subprocess.Process | None = None
    stderr: deque[str] = field(default_factory=lambda: deque[str](maxlen=STDERR_LINES))
    cancel_requested: bool = False
    killed: bool = False
    kill_timer: asyncio.TimerHandle | None = None
    task: asyncio.Task[None] | None = None
    queued: RunQueuedData | None = None
    """The last `run.queued` data published."""

    @property
    def run_id(self) -> str:
        return self.staged.run_id


@dataclass
class EndedRun:
    """A run that ended without a run directory: cancelled while queued, or its process exited early."""

    staged: StagedRun
    event: RunFailed | RunCancelled


def cut(text: str) -> str:
    return text if len(text) <= STDERR_MAX_CHARS else text[:STDERR_MAX_CHARS] + "…"


class RunManager:
    def __init__(
        self, runs_dir: Path, command: list[str], store: RunStore, config_dir: Path, grace: float = GRACE_SECONDS
    ) -> None:
        self.runs_dir = runs_dir
        self.command = command
        self.store = store
        self.config_dir = config_dir
        """Where `server-settings.json` holds `max_concurrent_runs`."""
        self.grace = grace
        self.queued: list[ActiveRun] = []
        """Staged runs, in staging order."""
        self.running: dict[str, ActiveRun] = {}
        """Run processes this server started, oldest first."""
        self.ended: OrderedDict[str, EndedRun] = OrderedDict()
        """Runs that ended without a run directory, newest last; in memory only."""
        self.stopping = False
        self.ticker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Queue every staged run again, oldest first, behind the runs already waiting; then start the tick."""
        for staged in staging.read_staged(self.runs_dir):
            if (self.runs_dir / staged.run_id).exists():
                staging.remove(self.runs_dir, staged.run_id)
                continue
            self.queued.append(self._active(staged))
        self._schedule()
        self.ticker = asyncio.get_running_loop().create_task(self._tick())

    async def submit(self, staged: StagedRun) -> ActiveRun:
        active = self._active(staged)
        self.queued.append(active)
        self._schedule()
        if active.queued is not None:
            log.info("run %s queued (position %d)", active.run_id, active.queued.position)
        return active

    def active(self, run_id: str) -> ActiveRun | None:
        return self.running.get(run_id) or next((run for run in self.queued if run.run_id == run_id), None)

    def limit(self) -> int:
        return global_settings.load(self.config_dir).max_concurrent_runs

    def queue_position(self, run_id: str) -> int | None:
        waiting = [run.run_id for run in self.queued]
        return waiting.index(run_id) + 1 if run_id in waiting else None

    def slot_state(self) -> SlotState:
        held = [
            SlotHolder(
                run_id=run.run_id,
                origin=run.staged.origin,
                token_name=run.staged.token_name,
                started=run.started or run.staged.created,
            )
            for run in self.running.values()
        ]
        queued = [
            SlotEntry(run_id=run.run_id, origin=run.staged.origin, token_name=run.staged.token_name)
            for run in self.queued
        ]
        return SlotState(limit=self.limit(), held=held, queued=queued)

    def queued_data(self, run_id: str) -> RunQueuedData | None:
        """`run.queued` data for a staged run; None when it does not wait."""
        position = self.queue_position(run_id)
        if position is None:
            return None
        state = self.slot_state()
        return RunQueuedData(position=position, limit=state.limit, held=state.held)

    async def cancel(self, run_id: str) -> Literal["signalled", "dequeued"] | None:
        """SIGTERM a running run (SIGKILL after the grace period); remove a queued one. None: not active."""
        if run_id in self.running:
            active = self.running[run_id]
            active.cancel_requested = True
            if active.process is not None:
                self._terminate(active)
            return "signalled"
        active = next((run for run in self.queued if run.run_id == run_id), None)
        if active is None:
            return None
        self.queued.remove(active)
        staging.remove(self.runs_dir, run_id)
        event = RunCancelled(seq=0, run_id=run_id, ts=datetime.now(UTC), data=RunCancelledData(stage=None))
        active.tail.publish(event)
        active.tail.close()
        self._remember(active.staged, event)
        log.info("run %s cancelled while queued", run_id)
        self._schedule()
        return "dequeued"

    def forget(self, run_id: str) -> bool:
        """Drop a remembered ended run; False when there is none."""
        return self.ended.pop(run_id, None) is not None

    async def shutdown(self) -> None:
        """SIGTERM every running run and wait up to the grace period; queued runs stay staged."""
        self.stopping = True
        if self.ticker is not None:
            self.ticker.cancel()
        tasks = [run.task for run in self.running.values() if run.task is not None]
        for active in list(self.running.values()):
            active.cancel_requested = True
            if active.process is not None:
                self._terminate(active)
        if tasks:
            await asyncio.wait(tasks, timeout=self.grace + 1)

    # Internals

    def _remember(self, staged: StagedRun, event: RunFailed | RunCancelled) -> None:
        self.ended[staged.run_id] = EndedRun(staged=staged, event=event)
        while len(self.ended) > ENDED_LIMIT:
            self.ended.popitem(last=False)

    def _active(self, staged: StagedRun) -> ActiveRun:
        return ActiveRun(staged=staged, tail=RunTail(staged.run_id, self.runs_dir / staged.run_id))

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(TICK_SECONDS)
            try:
                self._schedule()
            except Exception:
                log.exception("scheduling runs failed")

    def _schedule(self) -> None:
        """Start the oldest staged runs while fewer than the limit execute, then tell waiting runs their new data."""
        if self.stopping:
            return
        limit = self.limit()
        while self.queued and len(self.running) < limit:
            active = self.queued.pop(0)
            active.queued, active.started = None, datetime.now(UTC)
            active.argv = staging.build_argv(self.command, active.staged, self.runs_dir)
            self.running[active.run_id] = active
            active.task = asyncio.get_running_loop().create_task(self._run(active))
        for active in self.queued:
            active.queued = self._publish_queued(active.tail, active.queued)

    def _publish_queued(self, tail: RunTail, last: RunQueuedData | None) -> RunQueuedData | None:
        data = self.queued_data(tail.run_id)
        if data is not None and data != last:
            tail.publish(RunQueued(seq=tail.last_seq, run_id=tail.run_id, ts=datetime.now(UTC), data=data))
        return data

    def _terminate(self, active: ActiveRun) -> None:
        assert active.process is not None
        if active.process.returncode is not None or active.kill_timer is not None:
            return
        active.process.send_signal(signal.SIGTERM)
        active.kill_timer = asyncio.get_running_loop().call_later(self.grace, self._kill, active)

    def _kill(self, active: ActiveRun) -> None:
        if active.process is not None and active.process.returncode is None:
            active.killed = True
            active.process.kill()

    async def _run(self, active: ActiveRun) -> None:
        code: int | None = None
        try:
            code = await self._watch(active)
        except Exception:
            log.exception("run %s: watching the process failed", active.run_id)
        finally:
            self._finish(active, code)

    async def _watch(self, active: ActiveRun) -> int | None:
        """Spawn the process and poll its tail until it exits; its exit code, or None when it did not start."""
        try:
            process = await asyncio.create_subprocess_exec(
                *active.argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            active.stderr.append(str(error))
            return None
        active.process = process
        log.info("run %s started: %s pid %d", active.run_id, active.staged.kind.replace("rerun", "run"), process.pid)
        if active.cancel_requested:
            self._terminate(active)
        reader = asyncio.create_task(self._read_stderr(active, process))
        exited = asyncio.create_task(process.wait())
        while not exited.done():
            try:
                active.tail.poll()
            except Exception:
                log.exception("run %s: polling the run directory failed", active.run_id)
            await asyncio.wait({exited}, timeout=POLL_SECONDS)
        try:
            await reader
        except Exception:
            log.exception("run %s: reading standard error failed", active.run_id)
        return process.returncode

    async def _read_stderr(self, active: ActiveRun, process: asyncio.subprocess.Process) -> None:
        """Read in chunks so no line length can raise; a line over the cap is cut and the rest dropped."""
        assert process.stderr is not None
        pending, dropping = b"", False
        while chunk := await process.stderr.read(STDERR_CHUNK):
            *lines, pending = (pending + chunk).split(b"\n")
            for line in lines:
                if not dropping:
                    self._stderr_line(active, line)
                dropping = False
            if not dropping and len(pending) > STDERR_MAX_CHARS * 4:
                self._stderr_line(active, pending)
                pending, dropping = b"", True
            elif dropping:
                pending = b""
        if pending and not dropping:
            self._stderr_line(active, pending)

    def _stderr_line(self, active: ActiveRun, line: bytes) -> None:
        text = cut(line.decode("utf-8", errors="replace").rstrip("\r"))
        active.stderr.append(text)
        log.info("run %s: %s", active.run_id, text)

    def _finish(self, active: ActiveRun, code: int | None) -> None:
        """Log `run.failed` (or `run.cancelled` after a kill) when the process left no terminal event.

        Whatever fails here is logged; the tail is closed, staging removed, the run uncounted, and the queue pumped.
        """
        if active.kill_timer is not None:
            active.kill_timer.cancel()
        tail = active.tail
        try:
            self._finalise(active, code)
        except Exception:
            log.exception("run %s: finishing the run failed", active.run_id)
        self._log_end(active.run_id, tail.terminal_event)
        tail.close()
        staging.remove(self.runs_dir, active.run_id)
        self.running.pop(active.run_id, None)
        self._schedule()

    def _finalise(self, active: ActiveRun, code: int | None) -> None:
        tail = active.tail
        tail.poll()
        if tail.terminal_event is not None:
            return
        if active.killed:
            event_type, data = "run.cancelled", RunCancelledData(stage=None)
        else:
            error = f"process exited with code {code}" + "".join("\n" + line for line in active.stderr)
            event_type, data = "run.failed", RunFailedData(stage=None, error=error)
        if (self.runs_dir / active.run_id).is_dir():
            self.store.append_event(active.run_id, event_type, None, data)
            tail.poll()
            return
        now = datetime.now(UTC)
        event: RunFailed | RunCancelled
        if isinstance(data, RunFailedData):
            event = RunFailed(seq=0, run_id=active.run_id, ts=now, data=data)
        else:
            event = RunCancelled(seq=0, run_id=active.run_id, ts=now, data=data)
        tail.publish(event)
        self._remember(active.staged, event)

    def _log_end(self, run_id: str, event: Event | None) -> None:
        if isinstance(event, RunFailed):
            first = event.data.error.split("\n", 1)[0]
            log.warning("run %s failed in %s: %s", run_id, event.data.stage or "-", first)
        elif isinstance(event, RunCancelled):
            log.info("run %s cancelled", run_id)
        elif event is not None:
            log.info("run %s done", run_id)

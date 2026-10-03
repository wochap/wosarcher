"""The run queue: one subprocess per run, at most `limit` at once, FIFO, cancel by signal.

Scheduling is synchronous on the event loop (`_pump`), so no locks are needed.
Each started run gets one coroutine that polls its tail, waits for exit, and
finalises the log when the process ended without a terminal event.
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
)
from wosarcher.server import staging
from wosarcher.server.staging import StagedRun
from wosarcher.server.tail import RunTail
from wosarcher.store import RunStore

log = logging.getLogger(__name__)

POLL_SECONDS = 0.1
GRACE_SECONDS = 10.0
STDERR_LINES = 20
STDERR_MAX_CHARS = 4000
STDERR_CHUNK = 65536
ENDED_LIMIT = 100


@dataclass
class ActiveRun:
    staged: StagedRun
    tail: RunTail
    argv: list[str] = field(default_factory=list[str])
    process: asyncio.subprocess.Process | None = None
    stderr: deque[str] = field(default_factory=lambda: deque[str](maxlen=STDERR_LINES))
    cancel_requested: bool = False
    killed: bool = False
    kill_timer: asyncio.TimerHandle | None = None
    task: asyncio.Task[None] | None = None
    position: int | None = None
    """The last `run.queued` position broadcast."""

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
        self, runs_dir: Path, command: list[str], limit: int, store: RunStore, grace: float = GRACE_SECONDS
    ) -> None:
        self.runs_dir = runs_dir
        self.command = command
        self.limit = limit
        self.store = store
        self.grace = grace
        self.queued: list[ActiveRun] = []
        self.running: dict[str, ActiveRun] = {}
        self.ended: OrderedDict[str, EndedRun] = OrderedDict()
        """Runs that ended without a run directory, newest last; in memory only."""
        self.stopping = False

    async def start(self) -> None:
        """Queue every staged run again, oldest first; a staged run whose directory exists already started."""
        for staged in staging.read_staged(self.runs_dir):
            if (self.runs_dir / staged.run_id).exists():
                staging.remove(self.runs_dir, staged.run_id)
                continue
            self.queued.append(self._active(staged))
        self._pump()

    async def submit(self, staged: StagedRun) -> ActiveRun:
        active = self._active(staged)
        self.queued.append(active)
        self._pump()
        if active.position is not None:
            log.info("run %s queued (position %d)", active.run_id, active.position)
        return active

    def active(self, run_id: str) -> ActiveRun | None:
        return self.running.get(run_id) or next((run for run in self.queued if run.run_id == run_id), None)

    def queue_position(self, run_id: str) -> int | None:
        return next((n for n, run in enumerate(self.queued, 1) if run.run_id == run_id), None)

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
        self._pump()
        return "dequeued"

    def forget(self, run_id: str) -> bool:
        """Drop a remembered ended run; False when there is none."""
        return self.ended.pop(run_id, None) is not None

    async def shutdown(self) -> None:
        """SIGTERM every running run and wait up to the grace period; queued runs stay staged."""
        self.stopping = True
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

    def _pump(self) -> None:
        """Start queued runs while slots are free, then tell queued runs their new positions."""
        if self.stopping:
            return
        while self.queued and len(self.running) < self.limit:
            active = self.queued.pop(0)
            active.position = None
            active.argv = staging.build_argv(self.command, active.staged, self.runs_dir)
            self.running[active.run_id] = active
            active.task = asyncio.get_running_loop().create_task(self._run(active))
        for position, active in enumerate(self.queued, 1):
            if active.position != position:
                active.position = position
                data = RunQueuedData(position=position)
                now = datetime.now(UTC)
                active.tail.publish(RunQueued(seq=active.tail.last_seq, run_id=active.run_id, ts=now, data=data))

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

        Whatever fails here is logged; the tail is closed, staging removed, the slot freed, and the queue pumped.
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
        self._pump()

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

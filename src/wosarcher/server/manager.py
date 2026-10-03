"""The run queue: one subprocess per run, at most `limit` at once, FIFO, cancel by signal.

Scheduling is synchronous on the event loop (`_pump`), so no locks are needed.
Each started run gets one coroutine that polls its tail, waits for exit, and
finalises the log when the process ended without a terminal event.
"""

import asyncio
import signal
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from wosarcher.models import RunCancelled, RunCancelledData, RunFailed, RunFailedData, RunQueued, RunQueuedData
from wosarcher.server import staging
from wosarcher.server.staging import StagedRun
from wosarcher.server.tail import RunTail
from wosarcher.store import RunStore

POLL_SECONDS = 0.1
GRACE_SECONDS = 10.0
STDERR_LINES = 20


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
        last = active.tail.last_seq
        data = RunCancelledData(stage=None)
        active.tail.publish(RunCancelled(seq=last, run_id=run_id, ts=datetime.now(UTC), data=data))
        active.tail.close()
        self._pump()
        return "dequeued"

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
        try:
            process = await asyncio.create_subprocess_exec(
                *active.argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            active.stderr.append(str(error))
            self._finish(active, None)
            return
        active.process = process
        if active.cancel_requested:
            self._terminate(active)
        reader = asyncio.create_task(self._read_stderr(active, process))
        exited = asyncio.create_task(process.wait())
        while not exited.done():
            active.tail.poll()
            await asyncio.wait({exited}, timeout=POLL_SECONDS)
        await reader
        self._finish(active, process.returncode)

    async def _read_stderr(self, active: ActiveRun, process: asyncio.subprocess.Process) -> None:
        assert process.stderr is not None
        async for line in process.stderr:
            active.stderr.append(line.decode("utf-8", errors="replace").rstrip("\n"))

    def _finish(self, active: ActiveRun, code: int | None) -> None:
        """Log `run.failed` (or `run.cancelled` after a kill) when the process left no terminal event."""
        if active.kill_timer is not None:
            active.kill_timer.cancel()
        tail = active.tail
        tail.poll()
        if not tail.terminal:
            if active.killed:
                event_type, data = "run.cancelled", RunCancelledData(stage=None)
            else:
                error = f"process exited with code {code}" + "".join("\n" + line for line in active.stderr)
                event_type, data = "run.failed", RunFailedData(stage=None, error=error)
            if (self.runs_dir / active.run_id).is_dir():
                self.store.last_seq.pop(active.run_id, None)
                self.store.append_event(active.run_id, event_type, None, data)
                tail.poll()
            elif isinstance(data, RunFailedData):
                tail.publish(RunFailed(seq=tail.last_seq, run_id=active.run_id, ts=datetime.now(UTC), data=data))
            else:
                tail.publish(RunCancelled(seq=tail.last_seq, run_id=active.run_id, ts=datetime.now(UTC), data=data))
        tail.close()
        staging.remove(self.runs_dir, active.run_id)
        self.running.pop(active.run_id, None)
        self._pump()

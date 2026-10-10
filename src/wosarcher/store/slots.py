"""The shared run queue and run slots in `<runs_dir>/.slots/`, for every process that uses the runs directory.

    lock                              flock mutex for every slot decision
    queue/<created_ns>-<run_id>.json  a waiting run (ticket)
    held/<run_id>.json                a run holding a slot
    cancel/<run_id>                   a cancel request for that run

A ticket or slot file is live while some process holds `LOCK_EX` on it; the
kernel drops the lock when that process exits, even on SIGKILL. Files are
created under a temporary name, locked, written, and renamed, so no reader
sees an unlocked live entry. Only a process holding the mutex removes entries;
readers only test locks. The limit is read from the settings at each decision.
"""

import fcntl
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from wosarcher.models import SlotEntry, SlotHolder, SlotState
from wosarcher.store import settings

DIR = ".slots"


class SlotFile(BaseModel):
    entry: SlotEntry
    pid: int
    since: datetime


class Handle:
    """An open, locked ticket or slot file; closing it frees the place or the slot."""

    def __init__(self, slots: "Slots", path: Path, fd: int, run_id: str) -> None:
        self.slots = slots
        self.path = path
        self.fd = fd
        self.run_id = run_id

    def close(self) -> None:
        """Remove the file and the run's cancel request, then drop the lock."""
        if self.fd < 0:
            return
        with self.slots.mutex():
            self.path.unlink(missing_ok=True)
            (self.slots.root / "cancel" / self.run_id).unlink(missing_ok=True)
            os.close(self.fd)
        self.fd = -1

    def detach(self) -> None:
        """Close this copy of the descriptor only; a child that inherited it keeps the lock."""
        if self.fd >= 0:
            os.close(self.fd)
        self.fd = -1


class Ticket(Handle):
    """A place in the queue."""


class Held(Handle):
    def set_pid(self, pid: int) -> None:
        """Record the process that holds the slot (a child started with the inherited descriptor)."""
        found = read(self.path)
        if found is not None:
            data = found.model_copy(update={"pid": pid}).model_dump_json().encode()
            os.ftruncate(self.fd, 0)
            os.pwrite(self.fd, data, 0)

    @classmethod
    def inherit(cls, slots: "Slots", run_id: str, fd: int) -> "Held":
        return cls(slots, slots.root / "held" / f"{run_id}.json", fd, run_id)


def is_live(path: Path) -> bool:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    finally:
        os.close(fd)
    return False


def read(path: Path) -> SlotFile | None:
    try:
        return SlotFile.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        return None


class Slots:
    def __init__(self, runs_dir: Path, config_dir: Path | None) -> None:
        self.root = runs_dir / DIR
        self.config_dir = config_dir

    def limit(self) -> int:
        return settings.load(self.config_dir).max_concurrent_runs if self.config_dir else 1

    @contextmanager
    def mutex(self) -> Generator[None]:
        for name in ("queue", "held", "cancel"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        fd = os.open(self.root / "lock", os.O_RDWR | os.O_CREAT, 0o666)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def create(self, path: Path, entry: SlotEntry) -> int:
        """Write a locked entry file under a temporary name and rename it into place; its descriptor."""
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o666)
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, SlotFile(entry=entry, pid=os.getpid(), since=datetime.now(UTC)).model_dump_json().encode())
        temporary.rename(path)
        return fd

    def files(self, name: str) -> list[Path]:
        folder = self.root / name
        return sorted(p for p in folder.glob("*.json") if not p.name.startswith(".")) if folder.is_dir() else []

    def sweep(self) -> tuple[list[Path], list[Path]]:
        """Under the mutex: remove dead entries; the live tickets in order and the live slots."""
        live: dict[str, list[Path]] = {"queue": [], "held": []}
        for name, found in live.items():
            for path in self.files(name):
                if is_live(path):
                    found.append(path)
                else:
                    path.unlink(missing_ok=True)
        return live["queue"], live["held"]

    def ticket(self, entry: SlotEntry) -> Ticket:
        with self.mutex():
            path = self.root / "queue" / f"{time.time_ns():020d}-{entry.run_id}.json"
            return Ticket(self, path, self.create(path, entry), entry.run_id)

    def take(self, entry: SlotEntry) -> Held:
        path = self.root / "held" / f"{entry.run_id}.json"
        return Held(self, path, self.create(path, entry), entry.run_id)

    def grant(self, ticket: Ticket) -> Held | None:
        """One attempt: a slot when the ticket is the oldest live one and fewer than the limit are held."""
        with self.mutex():
            queue, held = self.sweep()
            if not queue or queue[0] != ticket.path or len(held) >= self.limit():
                return None
            found = read(ticket.path)
            entry = found.entry if found else SlotEntry(run_id=ticket.run_id, origin="cli")
            slot = self.take(entry)
            ticket.path.unlink(missing_ok=True)
        ticket.detach()
        return slot

    def try_take(self, entry: SlotEntry) -> Held | None:
        """A slot when one is free and no run waits, else None."""
        with self.mutex():
            queue, held = self.sweep()
            return None if queue or len(held) >= self.limit() else self.take(entry)

    def state(self) -> SlotState:
        """The limit, the live slots oldest first, and the live tickets in queue order."""
        held: list[SlotFile] = [f for p in self.files("held") if is_live(p) and (f := read(p))]
        queue = [f.entry for p in self.files("queue") if is_live(p) and (f := read(p))]
        holders = [SlotHolder(**f.entry.model_dump(), started=f.since) for f in sorted(held, key=lambda f: f.since)]
        return SlotState(limit=self.limit(), held=holders, queued=queue)

    def live(self, run_id: str) -> Literal["queued", "running"] | None:
        if is_live(self.root / "held" / f"{run_id}.json"):
            return "running"
        tickets = self.root / "queue"
        if tickets.is_dir() and any(is_live(path) for path in tickets.glob(f"*-{run_id}.json")):
            return "queued"
        return None

    def position(self, run_id: str) -> int | None:
        """The run's place in the queue (1 for the next to start); None when it does not wait."""
        queued = [entry.run_id for entry in self.state().queued]
        return queued.index(run_id) + 1 if run_id in queued else None

    def request_cancel(self, run_id: str) -> None:
        with self.mutex():
            (self.root / "cancel" / run_id).touch()

    def cancel_requested(self, run_id: str) -> bool:
        return (self.root / "cancel" / run_id).exists()

"""The run's event log: append through the store, then publish to live listeners."""

import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel

from wosarcher.models import Event, ReportSnapshot, ReportTextData, Stage, StageProgressData, make_event
from wosarcher.store import RunStore

Listener = Callable[[Event], None]
PROGRESS_INTERVAL = 0.25


class EventLog:
    def __init__(
        self,
        store: RunStore,
        run_id: str,
        listeners: Sequence[Listener] = (),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.run_id = run_id
        self.listeners = list(listeners)
        self.clock = clock
        self.progress_at: dict[Stage, float] = {}
        self.pending: dict[Stage, StageProgressData] = {}
        self.round = 1
        """The research round that `stage.progress` reports."""

    def publish(self, event: Event) -> None:
        for listener in self.listeners:
            listener(event)

    def emit(self, event_type: str, stage: Stage | None, data: BaseModel) -> Event:
        event = self.store.append_event(self.run_id, event_type, stage, data)
        self.publish(event)
        return event

    def live(self, event_type: str, stage: Stage | None, data: BaseModel) -> Event:
        """Publish without logging, with the last logged `seq` (for `report.delta`)."""
        seq = self.store.last_logged_seq(self.run_id)
        event = make_event(seq, self.run_id, datetime.now(UTC), event_type, stage, data)
        self.publish(event)
        return event

    def progress(self, stage: Stage, done: int, total: int, failed: int = 0) -> None:
        """At most one `stage.progress` per stage every 250 ms; `flush` sends the last one held back."""
        data = StageProgressData(done=done, total=total, failed=failed, round=self.round)
        now = self.clock()
        last = self.progress_at.get(stage)
        if last is not None and now - last < PROGRESS_INTERVAL:
            self.pending[stage] = data
            return
        self.progress_at[stage] = now
        self.pending.pop(stage, None)
        self.emit("stage.progress", stage, data)

    def flush(self, stage: Stage) -> None:
        data = self.pending.pop(stage, None)
        if data is not None:
            self.emit("stage.progress", stage, data)


def snapshot_event(store: RunStore, run_id: str) -> ReportSnapshot:
    """The report text so far, with the last logged `seq`, for a client that reconnects."""
    path = store.run_dir(run_id) / "report.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    seq = store.last_logged_seq(run_id)
    return ReportSnapshot(seq=seq, run_id=run_id, ts=datetime.now(UTC), stage="write", data=ReportTextData(text=text))

"""Follow one run directory: new lines of `events.jsonl` and new text of `report.md`, fanned out to subscribers.

The manager calls `poll()` every 100 ms while the run's process lives. Each
subscriber has its own queue; `None` in the queue ends the stream (the run
ended, or the subscriber fell too far behind and `overflowed` is set).
"""

import asyncio
import codecs
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from wosarcher.models import Event, ReportDelta, ReportSnapshot, ReportTextData, parse_event

MAX_BEHIND = 1000
TERMINAL = {"run.done", "run.failed", "run.cancelled"}


@dataclass
class Subscriber:
    last_seq: int
    """The last logged `seq` the tail had seen when the subscriber joined."""
    text: str
    """The report text at that moment."""
    queue: asyncio.Queue[Event | None] = field(default_factory=lambda: asyncio.Queue[Event | None]())
    overflowed: bool = False


class RunTail:
    def __init__(self, run_id: str, run_dir: Path, max_behind: int = MAX_BEHIND) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.max_behind = max_behind
        self.subscribers: list[Subscriber] = []
        self.offset = 0
        self.partial: bytes = b""
        self.last_seq = 0
        self.terminal = False
        self.report_bytes: bytes = b""
        self.report_text = ""
        self.decoder = codecs.getincrementaldecoder("utf-8")()

    def subscribe(self) -> Subscriber:
        """Register a subscriber; its queue holds exactly what happens after `last_seq` and `text`."""
        subscriber = Subscriber(last_seq=self.last_seq, text=self.report_text)
        self.subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        if subscriber in self.subscribers:
            self.subscribers.remove(subscriber)

    def publish(self, event: Event) -> None:
        for subscriber in self.subscribers:
            if subscriber.overflowed:
                continue
            if subscriber.queue.qsize() >= self.max_behind:
                subscriber.overflowed = True
                subscriber.queue.put_nowait(None)
                continue
            subscriber.queue.put_nowait(event)

    def close(self) -> None:
        """End every subscriber's stream."""
        for subscriber in self.subscribers:
            if not subscriber.overflowed:
                subscriber.queue.put_nowait(None)
        self.subscribers.clear()

    def poll(self) -> None:
        """Read the log, then the report, then publish report changes before events.

        The runner writes the report before logging the events that follow it, so
        this order never sends `run.done` before the final report text.
        """
        data = self.read_events()
        self.poll_report()
        self.publish_events(data)

    def read_events(self) -> bytes:
        path = self.run_dir / "events.jsonl"
        if not path.is_file():
            return b""
        with path.open("rb") as log:
            log.seek(self.offset)
            data = log.read()
        self.offset += len(data)
        return data

    def publish_events(self, data: bytes) -> None:
        *lines, self.partial = (self.partial + data).split(b"\n")
        for line in lines:
            if not line.strip():
                continue
            event = parse_event(line.decode("utf-8"))
            self.last_seq = event.seq
            self.terminal = self.terminal or event.type in TERMINAL
            self.publish(event)

    def poll_report(self) -> None:
        """Appended bytes become a `report.delta`; any other change becomes a `report.snapshot`."""
        path = self.run_dir / "report.md"
        data = path.read_bytes() if path.is_file() else b""
        if data == self.report_bytes:
            return
        now = datetime.now(UTC)
        if data.startswith(self.report_bytes):
            added = self.decoder.decode(data[len(self.report_bytes) :])
            self.report_bytes = data
            if added:
                self.report_text += added
                delta = ReportTextData(text=added)
                self.publish(ReportDelta(seq=self.last_seq, run_id=self.run_id, ts=now, stage="write", data=delta))
            return
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.report_bytes = data
        self.report_text = self.decoder.decode(data)
        snapshot = ReportTextData(text=self.report_text)
        self.publish(ReportSnapshot(seq=self.last_seq, run_id=self.run_id, ts=now, stage="write", data=snapshot))

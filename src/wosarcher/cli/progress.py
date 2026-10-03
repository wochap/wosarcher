"""Live progress on standard error: one row per stage, fed by run events."""

from dataclasses import dataclass

from rich.console import Console
from rich.live import Live
from rich.table import Table

from wosarcher.models import (
    STAGES,
    Event,
    PageFailed,
    PageFetched,
    ResourceWaiting,
    RunFailed,
    Stage,
    StageDone,
    StageFailed,
    StageProgress,
    StageStarted,
)


@dataclass
class Row:
    state: str = "pending"
    counters: str = ""
    device: str = ""
    provider: str = ""


class ProgressView:
    """A listener (`Callable[[Event], None]`) that redraws a rich table; use it as a context manager."""

    def __init__(self, console: Console) -> None:
        self.rows: dict[Stage, Row] = {stage: Row() for stage in STAGES}
        self.fetched = 0
        self.failed = 0
        self.live = Live(self.table(), console=console, transient=False, auto_refresh=False)

    def __enter__(self) -> "ProgressView":
        self.live.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.live.stop()

    def __call__(self, event: Event) -> None:
        self.update(event)
        self.live.update(self.table(), refresh=True)

    def update(self, event: Event) -> None:
        if event.stage is None:
            if isinstance(event, RunFailed) and event.data.stage is not None:
                self.rows[event.data.stage].state = "failed"
            return
        row = self.rows[event.stage]
        match event:
            case StageStarted():
                row.state, row.device, row.provider = "running", event.data.device or "", event.data.provider
            case StageProgress():
                failed = f", {event.data.failed} failed" if event.data.failed else ""
                row.counters = f"{event.data.done}/{event.data.total}{failed}"
            case PageFetched() | PageFailed():
                self.fetched += isinstance(event, PageFetched)
                self.failed += isinstance(event, PageFailed)
                row.counters = f"{self.fetched} pages, {self.failed} failed"
            case StageFailed():
                row.counters = f"fell back to {event.data.next}" if event.data.next else event.data.error
            case ResourceWaiting():
                row.state = f"waiting for {event.data.device}"
            case StageDone():
                data = event.data
                row.state = "copied" if data.copied_from else "skipped" if data.skipped else "done"
                row.counters = f"{data.count} in {data.seconds:.1f} s" if not data.copied_from else ""
                row.provider = data.provider or row.provider
            case _:
                pass

    def table(self) -> Table:
        table = Table("stage", "state", "counters", "device", "provider")
        for stage, row in self.rows.items():
            table.add_row(stage, row.state, row.counters, row.device, row.provider)
        return table

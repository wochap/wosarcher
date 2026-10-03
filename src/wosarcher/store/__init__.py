"""Run directories: request record, attachments, artifacts, the event log, forks, and listing.

Every JSON artifact is written to `<name>.tmp` and renamed. A stage counts as
finished only when its `stage.done` event is logged.
"""

import glob
import os
import secrets
import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from wosarcher.config import Settings, redact
from wosarcher.models import (
    STAGES,
    Event,
    RunCosts,
    RunRecord,
    RunRequest,
    RunStatus,
    RunSummary,
    Stage,
    StageDone,
    WritingOptions,
    make_event,
    parse_event,
)

STAGE_ARTIFACTS: dict[Stage, tuple[str, ...]] = {
    "load": ("files.jsonl",),
    "plan": ("plan.json", "initial.jsonl"),
    "search": ("hits.jsonl",),
    "fetch": ("pages.jsonl",),
    "chunk": ("chunks.jsonl",),
    "prefilter": ("candidates.jsonl",),
    "score": ("scores.jsonl",),
    "select": ("context.json",),
    "write": ("report.md", "report.json"),
}
END_STATUS: dict[str, RunStatus] = {"run.done": "done", "run.failed": "failed", "run.cancelled": "cancelled"}


class RunStoreError(Exception):
    pass


def new_run_id(now: datetime | None = None) -> str:
    """`YYYYMMDD-HHMMSS-xxxxxx`: UTC time, then microseconds in hex and one random hex digit, so IDs sort by time."""
    now = now or datetime.now(UTC)
    return f"{now:%Y%m%d-%H%M%S}-{now.microsecond:05x}{secrets.token_hex(1)[0]}"


def xdg(env: Mapping[str, str], name: str, fallback: str) -> Path:
    return Path(env.get(name) or Path(env.get("HOME", Path.home())) / fallback)


def expand(path: str) -> list[tuple[Path, Path]]:
    """(file, name under attachments/) for a file, a directory (recursively, keeping its layout), or a glob."""
    given = Path(path)
    if given.is_file():
        return [(given, Path(given.name))]
    if given.is_dir():
        files = [found for found in sorted(given.rglob("*")) if found.is_file()]
        visible = [found for found in files if not any(p.startswith(".") for p in found.relative_to(given).parts)]
        return [(found, Path(given.resolve().name) / found.relative_to(given)) for found in visible]
    matches = [Path(match) for match in sorted(glob.glob(path, recursive=True))]
    return [(match, Path(match.name)) for match in matches if match.is_file()]


def free_name(name: Path, taken: set[Path]) -> Path:
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = name.with_name(f"{name.stem}-{n}{name.suffix}")
    taken.add(candidate)
    return candidate


class RunStore:
    def __init__(self, runs_dir: Path, cache_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.cache_dir = cache_dir
        self.last_seq: dict[str, int] = {}

    @classmethod
    def from_settings(cls, settings: Settings, env: Mapping[str, str] = os.environ) -> "RunStore":
        runs = settings.run.runs_dir or xdg(env, "XDG_DATA_HOME", ".local/share") / "wosarcher" / "runs"
        cache = settings.run.cache_dir or xdg(env, "XDG_CACHE_HOME", ".cache") / "wosarcher"
        return cls(runs, cache)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    # Creation

    def new_dir(self, run_id: str | None) -> tuple[str, Path]:
        run_id = run_id or new_run_id()
        path = self.run_dir(run_id)
        if path.exists():
            raise RunStoreError(f"run directory {path} already exists")
        path.mkdir(parents=True)
        return run_id, path

    def create(
        self,
        request: RunRequest,
        profile: str,
        overrides: Sequence[str],
        settings: Settings,
        attachments: Sequence[str],
        run_id: str | None = None,
    ) -> RunRecord:
        copies: list[tuple[Path, Path]] = []
        taken: set[Path] = set()
        for path in attachments:
            found = expand(path)
            if not found:
                raise RunStoreError(f"--attach {path}: no file matches")
            copies.extend((file, free_name(name, taken)) for file, name in found)
        run_id, path = self.new_dir(run_id)
        for file, name in copies:
            (path / "attachments" / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, path / "attachments" / name)
        record = RunRecord(
            run_id=run_id,
            created_at=datetime.now(UTC),
            request=request.model_copy(update={"attachments": [name.as_posix() for _, name in copies]}),
            profile=profile,
            overrides=list(overrides),
            settings=redact(settings),
        )
        self.write_artifact(run_id, "request.json", record)
        return record

    def fork(
        self,
        parent_id: str,
        from_stage: Stage,
        overrides: Sequence[str],
        settings: Settings,
        *,
        profile: str | None = None,
        until: Stage | None = None,
        run_id: str | None = None,
    ) -> RunRecord:
        parent = self.read_record(parent_id)
        done = self.done_events(parent_id)
        earlier = STAGES[: STAGES.index(from_stage)]
        missing = [stage for stage in earlier if stage not in done]
        if missing:
            raise RunStoreError(f"cannot fork {parent_id} from {from_stage}: stage {missing[0]} is not finished")
        run_id, path = self.new_dir(run_id)
        source = self.run_dir(parent_id)
        if (source / "attachments").is_dir():
            shutil.copytree(source / "attachments", path / "attachments")
        record = RunRecord(
            run_id=run_id,
            created_at=datetime.now(UTC),
            request=parent.request.model_copy(update={"until": until}),
            profile=profile or parent.profile,
            overrides=[*parent.overrides, *overrides],
            changes=list(overrides),
            settings=redact(settings),
            parent_run_id=parent_id,
            fork_from=from_stage,
            version=parent.version + 1,
        )
        self.write_artifact(run_id, "request.json", record)
        for stage in earlier:
            for name in STAGE_ARTIFACTS[stage]:
                if (source / name).is_file():
                    shutil.copyfile(source / name, path / name)
            data = done[stage].data.model_copy(update={"copied_from": parent_id})
            self.append_event(run_id, "stage.done", stage, data)
        return record

    def read_record(self, run_id: str) -> RunRecord:
        path = self.run_dir(run_id) / "request.json"
        if not path.is_file():
            raise RunStoreError(f"no run {run_id} in {self.runs_dir}")
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

    # Artifacts

    def write_text(self, run_id: str, name: str, text: str) -> None:
        path = self.run_dir(run_id) / name
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)

    def write_artifact(self, run_id: str, name: str, value: BaseModel | Sequence[BaseModel]) -> None:
        if isinstance(value, BaseModel):
            text = value.model_dump_json(indent=2) + "\n"
        else:
            text = "".join(item.model_dump_json() + "\n" for item in value)
        self.write_text(run_id, name, text)

    def read_artifact[T: BaseModel](self, run_id: str, name: str, model_type: type[T]) -> T:
        return model_type.model_validate_json((self.run_dir(run_id) / name).read_text(encoding="utf-8"))

    def read_items[T: BaseModel](self, run_id: str, name: str, model_type: type[T]) -> list[T]:
        path = self.run_dir(run_id) / name
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [model_type.model_validate_json(line) for line in lines if line.strip()]

    def append_report(self, run_id: str, text: str) -> None:
        with (self.run_dir(run_id) / "report.md").open("a", encoding="utf-8") as report:
            report.write(text)
            report.flush()

    def write_costs(self, run_id: str, costs: RunCosts) -> None:
        self.write_artifact(run_id, "costs.json", costs)

    # Events

    def append_event(self, run_id: str, event_type: str, stage: Stage | None, data: BaseModel) -> Event:
        if run_id not in self.last_seq:
            events = self.read_events(run_id)
            self.last_seq[run_id] = events[-1].seq if events else 0
        event = make_event(self.last_seq[run_id] + 1, run_id, datetime.now(UTC), event_type, stage, data)
        with (self.run_dir(run_id) / "events.jsonl").open("a", encoding="utf-8") as log:
            log.write(event.model_dump_json() + "\n")
            log.flush()
        self.last_seq[run_id] = event.seq
        return event

    def last_logged_seq(self, run_id: str) -> int:
        if run_id not in self.last_seq:
            events = self.read_events(run_id)
            return events[-1].seq if events else 0
        return self.last_seq[run_id]

    def read_events(self, run_id: str, since: int = 0) -> list[Event]:
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.is_file():
            return []
        events = [parse_event(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [event for event in events if event.seq > since]

    def done_events(self, run_id: str) -> dict[Stage, StageDone]:
        return {e.stage: e for e in self.read_events(run_id) if isinstance(e, StageDone) and e.stage is not None}

    def finished_stages(self, run_id: str) -> set[Stage]:
        return set(self.done_events(run_id))

    # Listing

    def status(self, run_id: str) -> RunStatus:
        """From the last `run.*` event: started or queued without an end is `interrupted`."""
        runs = [event.type for event in self.read_events(run_id) if event.type.startswith("run.")]
        return END_STATUS.get(runs[-1], "interrupted") if runs else "interrupted"

    def read_costs(self, run_id: str) -> RunCosts | None:
        path = self.run_dir(run_id) / "costs.json"
        return RunCosts.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None

    def summary(self, record: RunRecord) -> RunSummary:
        """The run as listed: status and duration from the log, cost from `costs.json`."""
        events = [event for event in self.read_events(record.run_id) if event.type.startswith("run.")]
        status = END_STATUS.get(events[-1].type, "interrupted") if events else "interrupted"
        started = next((event.ts for event in events if event.type == "run.started"), None)
        duration = (events[-1].ts - started).total_seconds() if started and status != "interrupted" else None
        costs = self.read_costs(record.run_id)
        return RunSummary(
            run_id=record.run_id,
            query=record.request.query,
            status=status,
            created=record.created_at,
            parent_run_id=record.parent_run_id,
            version=record.version,
            fork_from=record.fork_from,
            profile=record.profile,
            sources=record.request.sources,
            until=record.request.until,
            writing=WritingOptions.model_validate(record.settings.get("write", {})),
            duration_s=duration,
            cost=costs.total.cost if costs else None,
        )

    def list_runs(self, limit: int | None = 20) -> list[RunSummary]:
        """Every run, newest first; directories starting with `.` (the server's `.queue/`) are skipped."""
        if not self.runs_dir.is_dir():
            return []
        found = [
            self.summary(self.read_record(path.name))
            for path in self.runs_dir.iterdir()
            if not path.name.startswith(".") and (path / "request.json").is_file()
        ]
        found.sort(key=lambda run: (run.created, run.run_id), reverse=True)
        return found[:limit]

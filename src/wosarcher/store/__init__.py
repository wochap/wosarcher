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
from typing import cast

from pydantic import BaseModel

from wosarcher.config import Settings, config_dir, redact
from wosarcher.models import (
    LOOP_STAGES,
    STAGES,
    Event,
    Origin,
    Plan,
    ReasoningOptions,
    ResearchDone,
    RunCancelled,
    RunCosts,
    RunFailed,
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
from wosarcher.store.slots import Slots

STAGE_ARTIFACTS: dict[Stage, tuple[str, ...]] = {
    "load": ("files.jsonl",),
    "plan": ("plan.json", "initial.jsonl"),
    "search": ("hits.jsonl",),
    "fetch": ("pages.jsonl",),
    "chunk": ("chunks.jsonl",),
    "prefilter": ("candidates.jsonl",),
    "score": ("scores.jsonl",),
    "gap": ("research.json",),
    "select": ("context.json", "select.jsonl"),
    "write": ("report.md", "report.json"),
}
END_STATUS: dict[str, RunStatus] = {"run.done": "done", "run.failed": "failed", "run.cancelled": "cancelled"}


TAIL_BLOCK = 8192


def line_seq(line: bytes) -> int | None:
    """The `seq` of one log line, or None when it is not an event."""
    if not line.strip():
        return None
    try:
        return parse_event(line.decode("utf-8")).seq
    except ValueError:
        return None


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


def settings_rounds(record: RunRecord) -> int:
    """The run's resolved `research.rounds`; 1 for runs from before research rounds."""
    research: object = record.settings.get("research")
    rounds = cast(dict[str, object], research).get("rounds", 1) if isinstance(research, dict) else 1
    return rounds if isinstance(rounds, int) else 1


def settings_llm(record: RunRecord) -> tuple[str, ReasoningOptions]:
    """The run's resolved `llm.model` and `llm.reasoning`; empty and `none` for runs from before them."""
    llm: object = record.settings.get("llm")
    block = cast(dict[str, object], llm) if isinstance(llm, dict) else {}
    model = block.get("model")
    reasoning = block.get("reasoning")
    options = ReasoningOptions.model_validate(reasoning) if isinstance(reasoning, dict) else ReasoningOptions()
    return (model if isinstance(model, str) else ""), options


def free_name(name: Path, taken: set[Path]) -> Path:
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = name.with_name(f"{name.stem}-{n}{name.suffix}")
    taken.add(candidate)
    return candidate


class RunStore:
    def __init__(self, runs_dir: Path, cache_dir: Path, config: Path | None = None) -> None:
        """`config`: the directory of `server-settings.json`, which holds the run slot limit."""
        self.runs_dir = runs_dir
        self.cache_dir = cache_dir
        self.slots = Slots(runs_dir, config)

    @classmethod
    def from_settings(cls, settings: Settings, env: Mapping[str, str] = os.environ) -> "RunStore":
        runs = settings.run.runs_dir or xdg(env, "XDG_DATA_HOME", ".local/share") / "wosarcher" / "runs"
        cache = settings.run.cache_dir or xdg(env, "XDG_CACHE_HOME", ".cache") / "wosarcher"
        return cls(runs, cache, config_dir(env))

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
        origin: Origin = "cli",
        token_name: str | None = None,
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
            origin=origin,
            token_name=token_name,
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
        origin: Origin = "cli",
        token_name: str | None = None,
    ) -> RunRecord:
        parent = self.read_record(parent_id)
        done = self.done_events(parent_id)
        missing = self.missing_stages(parent_id, from_stage)
        if missing:
            raise RunStoreError(f"cannot fork {parent_id} from {from_stage}: stage {missing[0]} is not finished")
        rerun_loop = from_stage in LOOP_STAGES and self.planned_rounds(parent) > 1
        earlier = STAGES[: STAGES.index("search" if rerun_loop else from_stage)]
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
            version=max(self.lineage_versions(parent_id)) + 1,
            origin=origin,
            token_name=token_name,
        )
        self.write_artifact(run_id, "request.json", record)
        for stage in earlier:
            for name in STAGE_ARTIFACTS[stage]:
                if (source / name).is_file():
                    shutil.copyfile(source / name, path / name)
            if stage not in done:
                continue
            data = done[stage].data.model_copy(update={"copied_from": done[stage].data.copied_from or parent_id})
            self.append_event(run_id, "stage.done", stage, data)
            research = self.research_done(parent_id)
            if stage == "gap" and research is not None:
                self.append_event(run_id, "research.done", "gap", research.data)
        if rerun_loop:
            plan = self.read_artifact(run_id, "plan.json", Plan)
            first = [query for query in plan.queries if query.round == 1]
            self.write_artifact(run_id, "plan.json", plan.model_copy(update={"queries": first}))
        return record

    def missing_stages(self, run_id: str, from_stage: Stage) -> list[Stage]:
        """The stages before `from_stage` that are not finished; `gap` only counts in multi-round runs."""
        finished = self.finished_stages(run_id)
        multi = self.planned_rounds(self.read_record(run_id)) > 1
        earlier = STAGES[: STAGES.index(from_stage)]
        if multi and from_stage in LOOP_STAGES:
            earlier = STAGES[: STAGES.index("search")]
        return [stage for stage in earlier if stage not in finished and (multi or stage != "gap")]

    def planned_rounds(self, record: RunRecord) -> int:
        """The rounds the loop runs: `research.rounds`, or 1 for files-only runs and plans without a sub-query."""
        if record.request.sources == "files" or settings_rounds(record) < 2:
            return 1
        path = self.run_dir(record.run_id) / "plan.json"
        if path.is_file() and len(self.read_artifact(record.run_id, "plan.json", Plan).queries) < 2:
            return 1
        return settings_rounds(record)

    def research_done(self, run_id: str) -> ResearchDone | None:
        return next((e for e in reversed(self.read_events(run_id)) if isinstance(e, ResearchDone)), None)

    def lineage_root(self, run_id: str) -> str:
        """Follow `parent_run_id` up, stopping at a missing or repeated run."""
        seen = [run_id]
        while True:
            path = self.run_dir(seen[-1]) / "request.json"
            if not path.is_file():
                return seen[-1]
            parent = RunRecord.model_validate_json(path.read_text(encoding="utf-8")).parent_run_id
            if parent is None or parent in seen or not (self.run_dir(parent) / "request.json").is_file():
                return seen[-1]
            seen.append(parent)

    def lineage_versions(self, run_id: str) -> list[int]:
        """Versions of every run whose parent chain reaches the root of `run_id`'s lineage."""
        root = self.lineage_root(run_id)
        records = {
            path.name: RunRecord.model_validate_json((path / "request.json").read_text(encoding="utf-8"))
            for path in self.runs_dir.iterdir()
            if not path.name.startswith(".") and (path / "request.json").is_file()
        }
        return [record.version for name, record in records.items() if self.lineage_root(name) == root]

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

    def append_jsonl(self, run_id: str, name: str, items: Sequence[BaseModel]) -> None:
        with (self.run_dir(run_id) / name).open("a", encoding="utf-8") as out:
            out.write("".join(item.model_dump_json() + "\n" for item in items))

    def read_artifact[T: BaseModel](self, run_id: str, name: str, model_type: type[T]) -> T:
        return model_type.model_validate_json((self.run_dir(run_id) / name).read_text(encoding="utf-8"))

    def read_items[T: BaseModel](self, run_id: str, name: str, model_type: type[T]) -> list[T]:
        path = self.run_dir(run_id) / name
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").split("\n")
        return [model_type.model_validate_json(line) for line in lines if line.strip()]

    def append_report(self, run_id: str, text: str) -> None:
        with (self.run_dir(run_id) / "report.md").open("a", encoding="utf-8") as report:
            report.write(text)
            report.flush()

    def write_costs(self, run_id: str, costs: RunCosts) -> None:
        self.write_artifact(run_id, "costs.json", costs)

    # Events

    def append_event(self, run_id: str, event_type: str, stage: Stage | None, data: BaseModel) -> Event:
        """Append with the next `seq` after the last complete line; a partial last line is closed first."""
        event = make_event(self.tail_seq(run_id) + 1, run_id, datetime.now(UTC), event_type, stage, data)
        path = self.run_dir(run_id) / "events.jsonl"
        with path.open("a+b") as log:
            prefix = b""
            if log.seek(0, os.SEEK_END) > 0:
                log.seek(-1, os.SEEK_END)
                prefix = b"" if log.read(1) == b"\n" else b"\n"
            log.write(prefix + event.model_dump_json().encode("utf-8") + b"\n")
            log.flush()
        return event

    def tail_seq(self, run_id: str) -> int:
        """The `seq` of the last complete line that parses, read backwards in 8 KiB blocks; 0 when none."""
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.is_file():
            return 0
        with path.open("rb") as log:
            end = log.seek(0, os.SEEK_END)
            buffer = b""
            while end > 0:
                start = max(0, end - TAIL_BLOCK)
                log.seek(start)
                buffer = log.read(end - start) + buffer
                end = start
                # The last piece has no "\n" yet; the first may be cut by the block boundary.
                lines = buffer.split(b"\n")[:-1]
                for line in reversed(lines if end == 0 else lines[1:]):
                    seq = line_seq(line)
                    if seq is not None:
                        return seq
        return 0

    def last_logged_seq(self, run_id: str) -> int:
        return self.tail_seq(run_id)

    def read_events(self, run_id: str, since: int = 0) -> list[Event]:
        """Every event after `since`; lines that do not parse (a partial line, an unknown type) are skipped."""
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.is_file():
            return []
        events: list[Event] = []
        for line in path.read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            try:
                event = parse_event(line)
            except ValueError:
                continue
            if event.seq > since:
                events.append(event)
        return events

    def done_events(self, run_id: str) -> dict[Stage, StageDone]:
        return {e.stage: e for e in self.read_events(run_id) if isinstance(e, StageDone) and e.stage is not None}

    def finished_stages(self, run_id: str) -> set[Stage]:
        """Stages with `stage.done`; in a multi-round run the loop stages count only after `research.done`."""
        finished = set(self.done_events(run_id))
        if self.planned_rounds(self.read_record(run_id)) > 1 and self.research_done(run_id) is None:
            finished -= set(LOOP_STAGES)
        return finished

    # Listing

    def status(self, run_id: str) -> RunStatus:
        """From the last `run.*` event; with no terminal event, from the run slots."""
        runs = [event.type for event in self.read_events(run_id) if event.type.startswith("run.")]
        return END_STATUS.get(runs[-1] if runs else "") or self.slots.live(run_id) or "interrupted"

    def read_costs(self, run_id: str) -> RunCosts | None:
        path = self.run_dir(run_id) / "costs.json"
        return RunCosts.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None

    def summary(self, record: RunRecord) -> RunSummary:
        """The run as listed: status and duration from the log, cost from `costs.json`."""
        events = [event for event in self.read_events(record.run_id) if event.type.startswith("run.")]
        ended_status = END_STATUS.get(events[-1].type) if events else None
        status = ended_status or self.slots.live(record.run_id) or "interrupted"
        started = next((event.ts for event in events if event.type == "run.started"), None)
        duration = (events[-1].ts - started).total_seconds() if started and ended_status else None
        costs = self.read_costs(record.run_id)
        research = self.research_done(record.run_id)
        gap_done = "gap" in self.done_events(record.run_id)
        last = events[-1] if events else None
        ended = last if isinstance(last, RunFailed | RunCancelled) else None
        error = last.data.error if isinstance(last, RunFailed) else None
        model, reasoning = settings_llm(record)
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
            depth=record.request.depth,
            writing=WritingOptions.model_validate(record.settings.get("write", {})),
            duration_s=duration,
            cost=costs.total.cost if costs else None,
            error=error,
            end_stage=ended.data.stage if ended else None,
            rounds_planned=settings_rounds(record),
            rounds_ran=research.data.ran if research else (1 if gap_done else None),
            stop_reason=research.data.reason if research else None,
            model=model,
            reasoning=reasoning,
            queue_position=self.slots.position(record.run_id) if status == "queued" else None,
            origin=record.origin,
            token_name=record.token_name,
        )

    def list_runs(self, limit: int | None = 20) -> list[RunSummary]:
        """Every run, newest first; directories starting with `.` (`.queue/`, `.slots/`) are skipped."""
        if not self.runs_dir.is_dir():
            return []
        found = [
            self.summary(self.read_record(path.name))
            for path in self.runs_dir.iterdir()
            if not path.name.startswith(".") and (path / "request.json").is_file()
        ]
        found.sort(key=lambda run: (run.created, run.run_id), reverse=True)
        return found[:limit]

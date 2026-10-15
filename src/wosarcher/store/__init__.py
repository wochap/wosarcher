"""Run directories: request record, attachments, artifacts, the event log, forks, and listing.

Every JSON artifact is written to `<name>.tmp` and renamed. A stage counts as
finished only when its `stage.done` event is logged.
"""

import fcntl
import glob
import os
import secrets
import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from wosarcher.config import LLM_KEYS, Settings, redact
from wosarcher.models import (
    CATALOG_STAGES,
    LOOP_STAGES,
    STAGES,
    WAVE_STAGES,
    AttachmentInfo,
    CatalogDone,
    CatalogRecord,
    Event,
    Limits,
    Node,
    Origin,
    Plan,
    ReasoningOptions,
    ResearchDone,
    RunCancelled,
    RunCosts,
    RunCreate,
    RunFailed,
    RunRecord,
    RunRequest,
    RunStatus,
    RunSummary,
    Stage,
    StageDone,
    Structure,
    WaveDone,
    WritingOptions,
    catalog_writes,
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
    "gap": ("research.json",),
    "select": ("context.json", "select.jsonl"),
    "write": ("report.md", "report.json"),
    "draft": ("structure.json", "nodes.jsonl"),
    "expand": ("plan.json",),
    "extract": ("records.jsonl",),
    "assemble": ("catalog.json",),
}
CATALOG_FORKS: tuple[Stage, ...] = ("expand", "extract")
"""The stages a catalog run forks from."""
CATALOG_COPIES: dict[Stage, tuple[str, ...]] = {
    "expand": (
        "files.jsonl",
        "structure.json",
        "nodes.jsonl",
        "records.jsonl",
        "plan.json",
        "hits.jsonl",
        "pages.jsonl",
        "chunks.jsonl",
    ),
    "extract": (
        "files.jsonl",
        "structure.json",
        "nodes.jsonl",
        "plan.json",
        "hits.jsonl",
        "pages.jsonl",
        "chunks.jsonl",
    ),
}
"""What a catalog fork copies; `nodes.jsonl` is rewritten after the copy."""
LIMIT_FLAGS = {"max_depth": "--max-depth", "max_nodes": "--max-nodes", "pages_per_node": "--pages-per-node"}
END_STATUS: dict[str, RunStatus] = {"run.done": "done", "run.failed": "failed", "run.cancelled": "cancelled"}
LOCK = ".lock"
"""`<run>/.lock`: the run process holds `LOCK_EX` on it until it exits; the kernel drops it even on SIGKILL."""


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


PROFILE_EDITS = ("use.", "llm.model", "llm.reasoning", *LLM_KEYS.values())


def modified(overrides: Sequence[str]) -> bool:
    """The overrides change an entry choice or an `llm` value the profile sets (the web's Advanced values)."""
    return any(override.strip().startswith(PROFILE_EDITS) for override in overrides)


def settings_llm(record: RunRecord) -> tuple[str, ReasoningOptions]:
    """The run's resolved `llm.model` and `llm.reasoning`; empty and `none` for runs from before them."""
    llm: object = record.settings.get("llm")
    block = cast(dict[str, object], llm) if isinstance(llm, dict) else {}
    model = block.get("model")
    reasoning = block.get("reasoning")
    options = ReasoningOptions.model_validate(reasoning) if isinstance(reasoning, dict) else ReasoningOptions()
    return (model if isinstance(model, str) else ""), options


def attachment_infos(folder: Path) -> list[AttachmentInfo]:
    """Each file under `folder` by its path relative to it, with its size; empty when the folder is missing."""
    if not folder.is_dir():
        return []
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    return [AttachmentInfo(name=path.relative_to(folder).as_posix(), size=path.stat().st_size) for path in files]


def free_name(name: Path, taken: set[Path]) -> Path:
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = name.with_name(f"{name.stem}-{n}{name.suffix}")
    taken.add(candidate)
    return candidate


def raised_limits(structure: Structure, limits: Mapping[str, int]) -> Structure:
    """The structure with `limits` applied; each at least the old value and at least one raised."""
    old = structure.limits
    unknown = [name for name in limits if name not in LIMIT_FLAGS]
    if unknown:
        raise RunStoreError(f"unknown limits: {', '.join(unknown)}")
    lower = [
        f"{LIMIT_FLAGS[name]} {value} < {getattr(old, name)}"
        for name, value in limits.items()
        if value < getattr(old, name)
    ]
    if lower:
        raise RunStoreError(f"a fork from expand cannot lower a limit: {'; '.join(lower)}")
    if not any(value > getattr(old, name) for name, value in limits.items()):
        raise RunStoreError(f"a fork from expand needs a raised limit: {', '.join(LIMIT_FLAGS.values())}")
    try:
        new = Limits.model_validate({**old.model_dump(), **limits})
    except ValueError as error:
        raise RunStoreError(f"invalid limits: {error}") from None
    return structure.model_copy(update={"limits": new})


def forked_nodes(nodes: Sequence[Node], structure: Structure, from_stage: Stage) -> list[Node]:
    """`extract`: every node `discovered`, `expanded` kept. `expand`: extracted nodes left unexpanded that the
    new limits make expandable go back to `discovered`."""
    if from_stage == "extract":
        return [node.model_copy(update={"status": "discovered", "reason": None}) for node in nodes]
    found: list[Node] = []
    for node in nodes:
        if node.status == "extracted" and not node.expanded and structure.is_expandable(node.type, node.depth):
            node = node.model_copy(update={"status": "discovered"})
        found.append(node)
    return found


class RunStore:
    def __init__(self, runs_dir: Path, cache_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.cache_dir = cache_dir
        self.locks: dict[str, int] = {}
        """Run locks this process holds, by run ID; never released before exit."""

    @classmethod
    def from_settings(cls, settings: Settings, env: Mapping[str, str] = os.environ) -> "RunStore":
        runs = settings.run.runs_dir or xdg(env, "XDG_DATA_HOME", ".local/share") / "wosarcher" / "runs"
        cache = settings.run.cache_dir or xdg(env, "XDG_CACHE_HOME", ".cache") / "wosarcher"
        return cls(runs, cache)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    # Creation

    def new_dir(self, run_id: str | None, lock: bool) -> tuple[str, Path]:
        """Create the run directory; with `lock`, hold its run lock before anything else is written."""
        run_id = run_id or new_run_id()
        path = self.run_dir(run_id)
        if path.exists():
            raise RunStoreError(f"run directory {path} already exists")
        path.mkdir(parents=True)
        if lock:
            self.lock(run_id)
        return run_id, path

    def lock(self, run_id: str) -> None:
        """Hold `LOCK_EX` on the run lock for the life of this process."""
        fd = os.open(self.run_dir(run_id) / LOCK, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.locks[run_id] = fd

    def is_running(self, run_id: str) -> bool:
        """Whether a process holds the run's lock."""
        try:
            fd = os.open(self.run_dir(run_id) / LOCK, os.O_RDONLY | os.O_CLOEXEC)
        except OSError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            os.close(fd)
        return False

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
        lock: bool = False,
        use: Mapping[str, str] | None = None,
        form: RunCreate | None = None,
    ) -> RunRecord:
        """With `lock`, this process holds the run lock (the engine); tests create runs without it."""
        copies: list[tuple[Path, Path]] = []
        taken: set[Path] = set()
        for path in attachments:
            found = expand(path)
            if not found:
                raise RunStoreError(f"--attach {path}: no file matches")
            copies.extend((file, free_name(name, taken)) for file, name in found)
        run_id, path = self.new_dir(run_id, lock)
        for file, name in copies:
            (path / "attachments" / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, path / "attachments" / name)
        record = RunRecord(
            run_id=run_id,
            created_at=datetime.now(UTC),
            request=request.model_copy(update={"attachments": [name.as_posix() for _, name in copies]}),
            profile=profile,
            use=dict(use) if use is not None else None,
            overrides=list(overrides),
            settings=redact(settings),
            origin=origin,
            token_name=token_name,
            form=form,
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
        lock: bool = False,
        use: Mapping[str, str] | None = None,
        limits: Mapping[str, int] | None = None,
    ) -> RunRecord:
        """`limits`: raised catalog limits (`max_depth`, `max_nodes`, `pages_per_node`), for `--from expand` only."""
        parent = self.read_record(parent_id)
        if parent.kind == "catalog":
            return self.fork_catalog(
                parent,
                from_stage,
                overrides,
                settings,
                limits=limits,
                profile=profile,
                until=until,
                run_id=run_id,
                origin=origin,
                token_name=token_name,
                lock=lock,
                use=use,
            )
        if limits:
            raise RunStoreError(f"{', '.join(LIMIT_FLAGS[name] for name in limits)}: only for catalog runs")
        done = self.done_events(parent_id)
        missing = self.missing_stages(parent_id, from_stage)
        if missing:
            raise RunStoreError(f"cannot fork {parent_id} from {from_stage}: stage {missing[0]} is not finished")
        rerun_loop = from_stage in LOOP_STAGES and self.planned_rounds(parent) > 1
        earlier = STAGES[: STAGES.index("search" if rerun_loop else from_stage)]
        run_id, path = self.new_dir(run_id, lock)
        source = self.run_dir(parent_id)
        if (source / "attachments").is_dir():
            shutil.copytree(source / "attachments", path / "attachments")
        record = RunRecord(
            run_id=run_id,
            created_at=datetime.now(UTC),
            request=parent.request.model_copy(update={"until": until}),
            profile=profile or parent.profile,
            use=dict(use) if use is not None else None,
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

    def fork_catalog(
        self,
        parent: RunRecord,
        from_stage: Stage,
        overrides: Sequence[str],
        settings: Settings,
        *,
        limits: Mapping[str, int] | None,
        profile: str | None,
        until: Stage | None,
        run_id: str | None,
        origin: Origin,
        token_name: str | None,
        lock: bool,
        use: Mapping[str, str] | None,
    ) -> RunRecord:
        """`expand`: everything copied, raised limits, nodes left unexpanded by the old limits back in the frontier.

        `extract`: the crawl's artifacts copied without the records, every node back to `discovered`.
        """
        parent_id = parent.run_id
        if from_stage not in CATALOG_FORKS:
            raise RunStoreError(
                f"cannot fork catalog run {parent_id} from {from_stage}: a catalog run forks from expand or extract"
            )
        missing = self.missing_stages(parent_id, from_stage)
        if missing:
            raise RunStoreError(f"cannot fork {parent_id} from {from_stage}: stage {missing[0]} is not finished")
        structure = self.read_artifact(parent_id, "structure.json", Structure)
        if from_stage == "expand":
            structure = raised_limits(structure, limits or {})
        elif limits:
            raise RunStoreError(f"{', '.join(LIMIT_FLAGS[name] for name in limits)}: only with --from expand")
        done = self.done_events(parent_id)
        run_id, path = self.new_dir(run_id, lock)
        source = self.run_dir(parent_id)
        if (source / "attachments").is_dir():
            shutil.copytree(source / "attachments", path / "attachments")
        record = RunRecord(
            run_id=run_id,
            created_at=datetime.now(UTC),
            request=parent.request.model_copy(update={"until": until, "structure": structure}),
            profile=profile or parent.profile,
            use=dict(use) if use is not None else None,
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
        for name in CATALOG_COPIES[from_stage]:
            if (source / name).is_file():
                shutil.copyfile(source / name, path / name)
        self.write_artifact(run_id, "structure.json", structure)
        nodes = self.read_items(run_id, "nodes.jsonl", Node)
        self.write_artifact(run_id, "nodes.jsonl", forked_nodes(nodes, structure, from_stage))
        for stage in ("load", "draft"):
            if stage in done:
                data = done[stage].data
                self.append_event(
                    run_id, "stage.done", stage, data.model_copy(update={"copied_from": data.copied_from or parent_id})
                )
        for event in self.read_events(parent_id):
            if isinstance(event, WaveDone):
                self.append_event(run_id, "wave.done", event.stage, event.data)
        return record

    def missing_stages(self, run_id: str, from_stage: Stage) -> list[Stage]:
        """The stages before `from_stage` that are not finished; `gap` only counts in multi-round runs."""
        finished = self.finished_stages(run_id)
        record = self.read_record(run_id)
        if record.kind == "catalog":
            needed: list[Stage] = ["load", "draft"] if from_stage == "expand" else ["load", "draft", "extract"]
            if from_stage == "extract" and not self.catalog_done(run_id):
                return ["assemble"]
            return [stage for stage in needed if stage not in finished and stage not in self.done_events(run_id)]
        multi = self.planned_rounds(record) > 1
        earlier = STAGES[: STAGES.index(from_stage)]
        if multi and from_stage in LOOP_STAGES:
            earlier = STAGES[: STAGES.index("search")]
        return [stage for stage in earlier if stage not in finished and (multi or stage != "gap")]

    def planned_rounds(self, record: RunRecord) -> int:
        """The rounds the loop runs: `research.rounds`, or 1 for files-only runs and plans without a sub-query."""
        if record.kind == "catalog" or record.request.sources == "files" or settings_rounds(record) < 2:
            return 1
        path = self.run_dir(record.run_id) / "plan.json"
        if path.is_file() and len(self.read_artifact(record.run_id, "plan.json", Plan).queries) < 2:
            return 1
        return settings_rounds(record)

    def catalog_done(self, run_id: str) -> CatalogDone | None:
        return next((e for e in reversed(self.read_events(run_id)) if isinstance(e, CatalogDone)), None)

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
        record = self.read_record(run_id)
        if record.kind == "catalog":
            if self.catalog_done(run_id) is None:
                finished -= {*WAVE_STAGES, "assemble"}
            return finished & set(CATALOG_STAGES)
        if self.planned_rounds(record) > 1 and self.research_done(run_id) is None:
            finished -= set(LOOP_STAGES)
        return finished

    # Listing

    def status(self, run_id: str) -> RunStatus:
        """From the last `run.*` event; with no terminal event, `running` while the run lock is held."""
        runs = [event.type for event in self.read_events(run_id) if event.type.startswith("run.")]
        return END_STATUS.get(runs[-1] if runs else "") or self.live(run_id)

    def live(self, run_id: str) -> RunStatus:
        return "running" if self.is_running(run_id) else "interrupted"

    def read_costs(self, run_id: str) -> RunCosts | None:
        path = self.run_dir(run_id) / "costs.json"
        return RunCosts.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None

    def summary(self, record: RunRecord) -> RunSummary:
        """The run as listed: status and duration from the log, cost from `costs.json`."""
        events = [event for event in self.read_events(record.run_id) if event.type.startswith("run.")]
        ended_status = END_STATUS.get(events[-1].type) if events else None
        status = ended_status or self.live(record.run_id)
        started = next((event.ts for event in events if event.type == "run.started"), None)
        duration = (events[-1].ts - started).total_seconds() if started and ended_status else None
        costs = self.read_costs(record.run_id)
        research = self.research_done(record.run_id)
        gap_done = "gap" in self.done_events(record.run_id)
        last = events[-1] if events else None
        ended = last if isinstance(last, RunFailed | RunCancelled) else None
        error = last.data.error if isinstance(last, RunFailed) else None
        model, reasoning = settings_llm(record)
        catalog = record.kind == "catalog"
        structure = record.request.structure
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
            kind=record.kind,
            writing=(
                WritingOptions.model_validate(record.settings.get("write", {}))
                if not catalog or catalog_writes(structure)
                else None
            ),
            output=structure.output if catalog and structure else None,
            nodes=self.node_count(record.run_id) if catalog else None,
            duration_s=duration,
            cost=costs.total.cost if costs else None,
            error=error,
            end_stage=ended.data.stage if ended else None,
            rounds_planned=settings_rounds(record),
            rounds_ran=research.data.ran if research else (1 if gap_done else None),
            stop_reason=research.data.reason if research else None,
            model=model,
            reasoning=reasoning,
            use=record.use,
            modified=modified(record.overrides),
            origin=record.origin,
            token_name=record.token_name,
            form=record.form,
            attachments=attachment_infos(self.run_dir(record.run_id) / "attachments"),
        )

    def node_count(self, run_id: str) -> int:
        """`catalog.json`'s record count when present, else the extracted nodes in `nodes.jsonl`."""
        if (self.run_dir(run_id) / "catalog.json").is_file():
            return len(self.read_artifact(run_id, "catalog.json", CatalogRecord).records)
        return sum(node.status == "extracted" for node in self.read_items(run_id, "nodes.jsonl", Node))

    def list_runs(self, limit: int | None = 20) -> list[RunSummary]:
        """Every run, newest first; directories starting with `.` (`.queue/`) are skipped."""
        if not self.runs_dir.is_dir():
            return []
        found = [
            self.summary(self.read_record(path.name))
            for path in self.runs_dir.iterdir()
            if not path.name.startswith(".") and (path / "request.json").is_file()
        ]
        found.sort(key=lambda run: (run.created, run.run_id), reverse=True)
        return found[:limit]

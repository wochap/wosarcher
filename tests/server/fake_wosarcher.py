"""A stand-in for `python -m wosarcher.daemon` that the server tests start as a real subprocess.

Accepts the `run`, `fork`, and `doctor --json` argv the server builds and writes
a run directory like the real runner: `request.json`, `attachments/`,
`events.jsonl` with increasing `seq`, and `report.md` appended in chunks and
then rewritten with the final text, then `context.json` and `report.json`. It also writes `argv.json`.

The runs directory is `WOSARCHER_RUN__RUNS_DIR`. The behaviour is the query
when it names a mode, else `FAKE_MODE`:

- `ok`: a short run that ends with `run.done`.
- `slow`: the same with a pause between chunks (`FAKE_STEP`, default 0.05 s).
- `crash`: `stage.started` for `score`, some standard error, exit code 1.
- `ignore-term`: ignores SIGTERM and waits to be killed.
- `bad-line`: writes `not json` to `events.jsonl` between two `stage.done` events, then ends with `run.done`.
- `huge-stderr`: prints one 100 000-character line to standard error, exit code 1.
- `early-exit`: prints `error: unknown profile 'x'` to standard error and exits with 2 before creating the run
  directory.
- `partial-kill`: like `ignore-term`, but first writes half an event line without a newline.

SIGTERM logs `run.cancelled` at the next chunk and exits 130. `doctor --json` prints a
`DoctorReport` chosen by `FAKE_DOCTOR` (`ok`, `slow`, `failed`, `hang`, or `garbage`),
limited to the `--block` names.
"""

import argparse
import json
import os
import shutil
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from wosarcher.config import ConfigError, list_entries, redact, resolve_run, without_use
from wosarcher.models import (
    CATALOG_STAGES,
    STAGES,
    CatalogDoneData,
    CatalogRecord,
    Context,
    DoctorReport,
    Node,
    ProviderHealth,
    Report,
    RunCancelledData,
    RunDoneData,
    RunRecord,
    RunRequest,
    RunStartedData,
    StageDoneData,
    StageProgressData,
    StageStartedData,
    Structure,
    UsageTotals,
)
from wosarcher.store import RunStore

MODES = ("ok", "slow", "crash", "ignore-term", "bad-line", "huge-stderr", "early-exit", "partial-kill")
CHUNKS = 20
FINAL_SUFFIX = "\n\n## References\n"


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("query")
    run.add_argument("--sources", default="both")
    run.add_argument("--attach", action="append", default=[])
    fork = commands.add_parser("fork")
    fork.add_argument("parent")
    fork.add_argument("--from", dest="from_stage", required=True)
    for command in (run, fork):
        command.add_argument("--run-id", required=True)
        command.add_argument("--until")
        command.add_argument("--profile")
        command.add_argument("--set", action="append", default=[])
        command.add_argument("--use", action="append", default=[])
        command.add_argument("--origin")
        command.add_argument("--token-name")
    run.add_argument("--form")
    run.add_argument("--depth")
    run.add_argument("--kind", default="research")
    run.add_argument("--structure")
    for command in (run, fork):
        for flag in ("--max-depth", "--max-nodes", "--pages-per-node"):
            command.add_argument(flag, type=int)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--profile")
    doctor.add_argument("--block", action="append", default=[])
    doctor.add_argument("--entry", action="append", default=[])
    doctor.add_argument("--all-entries", action="store_true")
    return parser.parse_args(argv)


def doctor(store: RunStore, argv: list[str], entries: list[str]) -> int:
    """Rows for the `--entry BLOCK=NAME` values, or every entry of `list_entries` with `--all-entries`."""
    store.runs_dir.mkdir(parents=True, exist_ok=True)
    (store.runs_dir / "doctor-argv.json").write_text(json.dumps(argv))
    kind = os.environ.get("FAKE_DOCTOR", "ok")
    if kind == "garbage":
        print("not json")
        return 1
    if kind == "hang":
        time.sleep(60)
    status = "failed" if kind == "failed" else "ok"
    latency = 1840 if kind == "slow" else 120
    rows = {
        "search": ProviderHealth(
            block="search", provider="searxng", base_url="http://s", status="ok", latency_ms=latency
        ),
        "fetch": ProviderHealth(block="fetch", provider="firecrawl", base_url="http://f", status="ok", latency_ms=90),
        "prefilter": ProviderHealth(block="prefilter", provider="embeddings", base_url="http://e", status="ok"),
        "score": ProviderHealth(block="score", provider="rerank", base_url="http://r", status=status, error="refused"),
        "llm": ProviderHealth(block="llm", provider="openai", base_url="http://l", status="ok", latency_ms=200),
    }
    if not entries:
        entries = [f"{block}={name}" for block, found in list_entries(os.environ).items() for name in found]
    chosen = [entry.partition("=") for entry in entries]
    report = DoctorReport(providers=tuple(rows[block].model_copy(update={"entry": name}) for block, _, name in chosen))
    print(report.model_dump_json(indent=2))
    return 1 if any(row.status == "failed" for row in report.providers) else 0


DERIVED = {
    "fields": [
        {"name": "name", "type": "text", "required": True},
        {"name": "type", "type": "enum", "values": ["ministry"]},
    ],
    "relation": "derived",
    "seeds": [{"name": "Derived", "type": "ministry"}],
}
"""The structure a catalog run without one gets, standing in for the draft call."""


def raised(parent: RunRecord, args: argparse.Namespace) -> Structure | None:
    """The parent's structure with the fork's limit flags over it."""
    if parent.request.structure is None:
        return None
    flags = {"max_depth": args.max_depth, "max_nodes": args.max_nodes, "pages_per_node": args.pages_per_node}
    limits = parent.request.structure.limits.model_copy(update={k: v for k, v in flags.items() if v is not None})
    return parent.request.structure.model_copy(update={"limits": limits})


def catalog(store: RunStore, record: RunRecord, first: str | None) -> int:
    """A catalog run: every catalog stage from `first`, one record per seed, then `catalog.done` and `run.done`."""
    run_id = record.run_id
    structure = record.request.structure or Structure.model_validate(DERIVED)
    store.write_artifact(run_id, "structure.json", structure)
    nodes = [
        Node(id=f"n{n}", name=seed.name, type=seed.type, status="extracted") for n, seed in enumerate(structure.seeds)
    ]
    store.write_text(run_id, "nodes.jsonl", "".join(node.model_dump_json() + "\n" for node in nodes))
    start = CATALOG_STAGES.index(first) if first else 0
    until = record.request.until
    end = CATALOG_STAGES.index(until) + 1 if until else len(CATALOG_STAGES)
    for stage in CATALOG_STAGES[start:end]:
        store.append_event(run_id, "stage.done", stage, StageDoneData(count=0, seconds=0))
    if end < len(CATALOG_STAGES):
        store.append_event(run_id, "run.done", None, RunDoneData(until=until, totals=UsageTotals()))
        return 0
    records = [{"id": node.id, "name": node.name, "type": node.type} for node in nodes]
    catalog = CatalogRecord(records=records, nodes=len(nodes), reason="frontier empty", output=structure.output)
    store.write_artifact(run_id, "catalog.json", catalog)
    if structure.wants_report:
        body = f"{nodes[0].name} heads the catalog [1]."
        report = Report(body=body, markdown=body + "\n\n## References\n", cited=[1], references=[], records=True)
        store.write_text(run_id, "report.md", report.markdown)
        store.write_artifact(run_id, "report.json", report)
    done = CatalogDoneData(waves=1, nodes=len(nodes), records=len(nodes), flagged=0, reason="frontier empty", note="")
    store.append_event(run_id, "catalog.done", "assemble", done)
    store.append_event(run_id, "run.done", None, RunDoneData(until=record.request.until, totals=UsageTotals()))
    return 0


def create(store: RunStore, args: argparse.Namespace) -> RunRecord:
    run_dir = store.run_dir(args.run_id)
    if run_dir.exists():
        sys.exit(2)
    if args.command == "run":
        try:
            resolve_run(args.profile, [*args.set, *(f"use.{choice}" for choice in args.use)], os.environ)
        except ConfigError as error:
            print(f"error: {error}", file=sys.stderr)
            sys.exit(2)
    run_dir.mkdir(parents=True)
    store.lock(args.run_id)
    names: list[str] = []
    for path in map(Path, getattr(args, "attach", [])):
        (run_dir / "attachments").mkdir(exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, run_dir / "attachments" / path.name)
        else:
            shutil.copyfile(path, run_dir / "attachments" / path.name)
        names.append(path.name)
    depth = getattr(args, "depth", None)
    if args.command == "fork":
        parent = store.read_record(args.parent)
        request = parent.request.model_copy(update={"until": args.until, "structure": raised(parent, args)})
        lineage = {"parent_run_id": args.parent, "fork_from": args.from_stage, "version": parent.version + 1}
        profile, overrides = args.profile or parent.profile, [*without_use(parent.overrides), *args.set]
    else:
        structure = Structure.model_validate_json(args.structure) if args.structure else None
        request = RunRequest(
            query=args.query,
            sources=args.sources,
            until=args.until,
            attachments=names,
            depth=depth,
            kind=args.kind,
            structure=structure,
        )
        lineage = {}
        profile, overrides = args.profile or "workstation", args.set
    overrides += [f"use.{choice}" for choice in args.use]
    resolved = resolve_run("workstation", overrides, os.environ, request.depth)
    record = RunRecord.model_validate(
        {
            "run_id": args.run_id,
            "created_at": datetime.now(UTC),
            "request": request,
            "profile": profile,
            "use": resolved.use,
            "overrides": overrides,
            "settings": redact(resolved.settings),
            "origin": args.origin or "cli",
            "token_name": args.token_name,
            "form": json.loads(args.form) if getattr(args, "form", None) else None,
            **lineage,
        }
    )
    store.write_artifact(args.run_id, "request.json", record)
    return record


def main(argv: list[str]) -> int:
    store = RunStore(Path(os.environ["WOSARCHER_RUN__RUNS_DIR"]), Path())
    args = parse(argv)
    if args.command == "doctor":
        return doctor(store, argv, args.entry)
    query = getattr(args, "query", None)
    if (query if query in MODES else os.environ.get("FAKE_MODE")) == "early-exit":
        print("error: unknown profile 'x'", file=sys.stderr)
        return 2
    record = create(store, args)
    run_id = record.run_id
    (store.run_dir(run_id) / "argv.json").write_text(json.dumps(argv))
    mode = record.request.query if record.request.query in MODES else os.environ.get("FAKE_MODE", "ok")
    waits = mode in ("ignore-term", "partial-kill")
    step = float(os.environ.get("FAKE_STEP", "0.05")) if mode == "slow" or waits else 0.0

    cancelled: list[int] = []

    def cancel(signum: int, _frame: object) -> None:
        cancelled.append(signum)

    signal.signal(signal.SIGTERM, signal.SIG_IGN if waits else cancel)
    started = RunStartedData(
        query=record.request.query,
        profile=record.profile,
        parent_run_id=record.parent_run_id,
        version=record.version,
        until=record.request.until,
    )
    store.append_event(run_id, "run.started", None, started)
    if mode == "crash":
        store.append_event(run_id, "stage.started", "score", StageStartedData(device=None, provider="rerank"))
        for n in range(30):
            print(f"traceback line {n}", file=sys.stderr)
        return 1
    if record.request.kind == "catalog":
        return catalog(store, record, args.from_stage if args.command == "fork" else None)
    if mode == "huge-stderr":
        print("x" * 100_000, file=sys.stderr)
        return 1
    first = STAGES.index(args.from_stage) if args.command == "fork" else 0
    for stage in STAGES[first:-1]:
        store.append_event(run_id, "stage.done", stage, StageDoneData(count=0, seconds=0))
        if mode == "bad-line" and stage == STAGES[first]:
            with (store.run_dir(run_id) / "events.jsonl").open("a", encoding="utf-8") as log:
                log.write("not json\n")
    store.append_event(run_id, "stage.started", "write", StageStartedData(device=None, provider="openai"))
    streamed = ""
    for n in range(CHUNKS):
        if cancelled:
            store.append_event(run_id, "run.cancelled", None, RunCancelledData(stage="write"))
            return 130
        chunk = f"Part {n} é→ "
        store.append_report(run_id, chunk)
        streamed += chunk
        store.append_event(run_id, "stage.progress", "write", StageProgressData(done=n + 1, total=CHUNKS, failed=0))
        time.sleep(step)
    if mode == "partial-kill":
        with (store.run_dir(run_id) / "events.jsonl").open("a", encoding="utf-8") as log:
            log.write('{"seq": 999, "run_id": "')
    while waits:
        time.sleep(step)
    store.write_text(run_id, "report.md", streamed + FINAL_SUFFIX)
    context = Context(query=record.request.query, passages=[], sources=[], budget_tokens=100, used_tokens=0)
    store.write_artifact(run_id, "context.json", context)
    report = Report(body=streamed, markdown=streamed + FINAL_SUFFIX, cited=[], references=[])
    store.write_artifact(run_id, "report.json", report)
    store.append_event(run_id, "stage.done", "write", StageDoneData(count=1, seconds=0.1))
    store.append_event(run_id, "run.done", None, RunDoneData(until=record.request.until, totals=UsageTotals()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

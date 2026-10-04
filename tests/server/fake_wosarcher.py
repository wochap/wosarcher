"""A stand-in for `python -m wosarcher` that the server tests start as a real subprocess.

Accepts the `run`, `fork`, and `doctor --json` argv the server builds and writes
a run directory like the real runner: `request.json`, `attachments/`,
`events.jsonl` with increasing `seq`, and `report.md` appended in chunks and
then rewritten with the final text. It also writes `argv.json`.

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

from wosarcher.config import override_layer
from wosarcher.models import (
    STAGES,
    DoctorReport,
    ProviderHealth,
    RunCancelledData,
    RunDoneData,
    RunRecord,
    RunRequest,
    RunStartedData,
    StageDoneData,
    StageProgressData,
    StageStartedData,
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
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--profile")
    doctor.add_argument("--block", action="append", default=[])
    return parser.parse_args(argv)


def doctor(store: RunStore, argv: list[str], chosen: list[str]) -> int:
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
    rows = (
        ProviderHealth(block="search", provider="searxng", base_url="http://s", status="ok", latency_ms=latency),
        ProviderHealth(block="fetch", provider="firecrawl", base_url="http://f", status="ok", latency_ms=90),
        ProviderHealth(block="prefilter", provider="embeddings", base_url="http://e", status="ok", latency_ms=30),
        ProviderHealth(block="score", provider="rerank", base_url="http://r", status=status, error="refused"),
        ProviderHealth(block="llm", provider="llm", base_url="http://l", status="ok", latency_ms=200),
    )
    rows = tuple(row for row in rows if not chosen or row.block in chosen)
    print(DoctorReport(providers=rows).model_dump_json(indent=2))
    return 1 if status == "failed" else 0


def create(store: RunStore, args: argparse.Namespace) -> RunRecord:
    run_dir = store.run_dir(args.run_id)
    if run_dir.exists():
        sys.exit(2)
    run_dir.mkdir(parents=True)
    names: list[str] = []
    for path in map(Path, getattr(args, "attach", [])):
        (run_dir / "attachments").mkdir(exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, run_dir / "attachments" / path.name)
        else:
            shutil.copyfile(path, run_dir / "attachments" / path.name)
        names.append(path.name)
    tree, _ = override_layer(args.set)
    if args.command == "fork":
        parent = store.read_record(args.parent)
        request = parent.request.model_copy(update={"until": args.until})
        lineage = {"parent_run_id": args.parent, "fork_from": args.from_stage, "version": parent.version + 1}
        profile, overrides = args.profile or parent.profile, [*parent.overrides, *args.set]
    else:
        request = RunRequest(query=args.query, sources=args.sources, until=args.until, attachments=names)
        lineage = {}
        profile, overrides = args.profile or "workstation", args.set
    record = RunRecord.model_validate(
        {
            "run_id": args.run_id,
            "created_at": datetime.now(UTC),
            "request": request,
            "profile": profile,
            "overrides": overrides,
            "settings": {"write": tree.get("write", {})},
            **lineage,
        }
    )
    store.write_artifact(args.run_id, "request.json", record)
    return record


def main(argv: list[str]) -> int:
    store = RunStore(Path(os.environ["WOSARCHER_RUN__RUNS_DIR"]), Path())
    args = parse(argv)
    if args.command == "doctor":
        return doctor(store, argv, args.block)
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
    if mode == "huge-stderr":
        print("x" * 100_000, file=sys.stderr)
        return 1
    first = STAGES.index(args.from_stage) if args.command == "fork" else 0
    for stage in STAGES[first:-1]:
        store.append_event(run_id, "stage.done", stage, StageDoneData(count=0, seconds=0))
        if mode == "bad-line" and stage == STAGES[first]:
            with (store.run_dir(run_id) / "events.jsonl").open("a", encoding="utf-8") as log:
                log.write("not json\n")
    store.append_event(run_id, "stage.started", "write", StageStartedData(device=None, provider="llm"))
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
    store.append_event(run_id, "stage.done", "write", StageDoneData(count=1, seconds=0.1))
    store.append_event(run_id, "run.done", None, RunDoneData(until=record.request.until, totals=UsageTotals()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

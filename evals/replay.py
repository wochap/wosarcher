"""Replay recorded runs with ranking variants through `wosarcher fork`.

    python -m evals.replay (--runs ID... | --all) --variants NAME... --out DIR [--write] [--force]

Each (run, variant) pair becomes one line of `<out>/results.jsonl`; pairs
already there are skipped unless `--force` is given. Forks run one at a
time so model variants do not compete and timings stay comparable.

A fork that ends `done` is still recorded as `failed` when its events show
that it did not rank with the configured scorer or prefilter: the score
stage fell back, or the prefilter ran another method.
"""

import argparse
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, ValidationError

from wosarcher.config import ConfigError, resolve
from wosarcher.models import RunOutput, RunRecord, StageDone, StageFailed, parse_event
from wosarcher.store import RunStore

VARIANTS = Path(__file__).parent / "variants.toml"
ForkStage = Literal["chunk", "prefilter", "score"]
ERROR_CHARS = 2000


class VariantError(ValueError):
    pass


class Variant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    from_stage: ForkStage
    set: list[str] = []


class ForkResult(BaseModel):
    """One line of `results.jsonl`."""

    parent_run_id: str
    variant: str
    run_id: str | None
    status: Literal["done", "failed", "cancelled"]
    error: str | None = None
    run_dir: str | None = None


def load_variants(path: Path) -> dict[str, Variant]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    variants: dict[str, Variant] = {}
    for name, table in data.items():
        if not isinstance(table, dict):
            raise VariantError(f"variant '{name}' in {path} must be a table")
        fields = cast(dict[str, Any], table)
        stage = fields.get("from")
        if stage not in get_args(ForkStage):
            allowed = ", ".join(get_args(ForkStage))
            raise VariantError(f"variant '{name}' in {path}: from must be one of {allowed}, not {stage!r}")
        try:
            rest = {key: value for key, value in fields.items() if key != "from"}
            variants[name] = Variant.model_validate({"name": name, "from_stage": stage, **rest})
        except ValidationError as error:
            raise VariantError(f"variant '{name}' in {path}: {error}") from None
    return variants


def fork(
    run_id: str, variant: Variant, *, write: bool, env: Mapping[str, str], extra: Sequence[str] = ()
) -> ForkResult:
    """Run `wosarcher fork` in a subprocess; a failure is a result, not an exception."""
    args = [sys.executable, "-m", "wosarcher", "fork", run_id, "--from", variant.from_stage, "--json"]
    if not write:
        args += ["--until", "select"]
    for item in [*extra, *variant.set]:
        args += ["--set", item]
    done = subprocess.run(args, capture_output=True, text=True, env=dict(env), check=False)
    try:
        output = RunOutput.model_validate_json(done.stdout)
    except ValidationError:
        error = done.stderr.strip()[-ERROR_CHARS:] or f"exit status {done.returncode}"
        return ForkResult(parent_run_id=run_id, variant=variant.name, run_id=None, status="failed", error=error)
    status, error = output.status, output.error
    if status == "done":
        error = fallback_error(Path(output.run_dir))
        status = "failed" if error else "done"
    return ForkResult(
        parent_run_id=run_id,
        variant=variant.name,
        run_id=output.run_id,
        status=status,
        error=error,
        run_dir=output.run_dir,
    )


def fallback_error(run_dir: Path) -> str | None:
    """Why a finished fork did not measure the configured ranking, or None when it did."""
    settings = RunRecord.model_validate_json((run_dir / "request.json").read_text(encoding="utf-8")).settings
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    events = [parse_event(line) for line in lines if line.strip()]
    ran = [e for e in events if isinstance(e, StageDone) and not e.data.skipped and not e.data.copied_from]
    failed = [e for e in events if isinstance(e, StageFailed) and e.stage == "score"]
    if failed:
        scorer = next((e.data.provider for e in reversed(ran) if e.stage == "score"), None) or failed[-1].data.next
        return f"score ran {scorer} instead of {settings['score']['provider']}: {failed[0].data.error}"
    configured = settings["prefilter"]["provider"]
    for event in ran:
        method = (event.data.provider or "").split(":")[0]
        if event.stage == "prefilter" and method and method != configured:
            return f"prefilter ran {method} instead of {configured}"
    return None


def read_results(path: Path) -> list[ForkResult]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").split("\n")
    return [ForkResult.model_validate_json(line) for line in lines if line.strip()]


def recorded_runs(store: RunStore) -> list[str]:
    """Runs that are not forks and finished `select`, oldest first."""
    found = [run for run in store.list_runs(limit=sys.maxsize) if run.version == 1]
    return [run.run_id for run in reversed(found) if "select" in store.finished_stages(run.run_id)]


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m evals.replay", description="Replay recorded runs with ranking variants."
    )
    runs = parser.add_mutually_exclusive_group(required=True)
    runs.add_argument("--runs", nargs="+", metavar="ID", help="Recorded runs to replay.")
    runs.add_argument("--all", action="store_true", help="Every recorded run (version 1) that finished select.")
    parser.add_argument("--variants", nargs="+", required=True, metavar="NAME")
    parser.add_argument("--variants-file", type=Path, default=VARIANTS)
    parser.add_argument("--out", type=Path, required=True, help="Directory for results.jsonl.")
    parser.add_argument("--write", action="store_true", help="Run the forks through the write stage.")
    parser.add_argument("--force", action="store_true", help="Replay pairs that already have a result.")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="Passed to every fork.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        variants = load_variants(args.variants_file)
        unknown = [name for name in args.variants if name not in variants]
        if unknown:
            raise VariantError(f"unknown variant {', '.join(unknown)}; known: {', '.join(variants)}")
        runs: list[str] = args.runs or recorded_runs(RunStore.from_settings(resolve(None, args.set, os.environ)))
    except (VariantError, ConfigError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "results.jsonl"
    finished = {(result.parent_run_id, result.variant) for result in read_results(path)}
    for run_id in runs:
        for name in args.variants:
            if (run_id, name) in finished and not args.force:
                continue
            result = fork(run_id, variants[name], write=args.write, env=os.environ, extra=args.set)
            with path.open("a", encoding="utf-8") as out:
                out.write(result.model_dump_json() + "\n")
            print(json.dumps({"run": run_id, "variant": name, "status": result.status}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

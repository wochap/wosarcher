"""Metrics without an LLM over replay results.

    python -m evals.metrics --results DIR [--baseline NAME]

Reads `<DIR>/results.jsonl`, writes `<DIR>/metrics.json`, and prints a
Markdown table with one row per variant.
"""

import argparse
import math
import statistics
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from evals.replay import ForkResult, read_results
from wosarcher.models import Context, Stage, StageDone, parse_event

CHARS_PER_TOKEN = 4


class ResultMetrics(BaseModel):
    parent_run_id: str
    variant: str
    run_id: str | None
    status: str
    passages: int = 0
    chars: int = 0
    tokens: int = 0
    seconds: dict[Stage, float] = {}
    """Stages the fork ran; copied stages are left out."""
    overlap: dict[str, float] = {}
    """Jaccard of selected chunk IDs against each other variant on the same parent run."""


def context(run_dir: Path) -> Context | None:
    path = run_dir / "context.json"
    return Context.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None


def selected_chunk_ids(run_dir: Path) -> list[str]:
    found = context(run_dir)
    return [passage.chunk_id for passage in found.passages] if found else []


def context_size(run_dir: Path) -> tuple[int, int]:
    """Characters of the selected passages, and estimated tokens: characters / 4, rounded up."""
    found = context(run_dir)
    chars = sum(len(passage.text) for passage in found.passages) if found else 0
    return chars, math.ceil(chars / CHARS_PER_TOKEN)


def stage_seconds(run_dir: Path) -> dict[Stage, float]:
    path = run_dir / "events.jsonl"
    lines = path.read_text(encoding="utf-8").split("\n") if path.is_file() else []
    events = [parse_event(line) for line in lines if line.strip()]
    return {
        event.stage: event.data.seconds
        for event in events
        if isinstance(event, StageDone) and event.stage is not None and event.data.copied_from is None
    }


def jaccard(a: set[str], b: set[str]) -> float:
    """Overlap of two sets; 1.0 when both are empty."""
    return len(a & b) / len(a | b) if a or b else 1.0


def measure(results: Sequence[ForkResult]) -> list[ResultMetrics]:
    measured: list[ResultMetrics] = []
    chosen: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for result in results:
        item = ResultMetrics(
            parent_run_id=result.parent_run_id, variant=result.variant, run_id=result.run_id, status=result.status
        )
        if result.status == "done" and result.run_dir:
            run_dir = Path(result.run_dir)
            ids = selected_chunk_ids(run_dir)
            chars, tokens = context_size(run_dir)
            seconds = stage_seconds(run_dir)
            item = item.model_copy(update={"passages": len(ids), "chars": chars, "tokens": tokens, "seconds": seconds})
            chosen[result.parent_run_id][result.variant] = set(ids)
        measured.append(item)
    for item in measured:
        if item.status != "done":
            continue
        variants = chosen[item.parent_run_id]
        mine = variants.get(item.variant, set())
        item.overlap.update({name: jaccard(mine, ids) for name, ids in variants.items() if name != item.variant})
    return measured


def p90(values: Sequence[float]) -> float:
    """Nearest-rank 90th percentile."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


def cell(values: Sequence[float], digits: int = 1) -> str:
    return f"{statistics.median(values):.{digits}f}" if values else "-"


def summarise(measured: Sequence[ResultMetrics], baseline: str | None = None) -> str:
    """Markdown table, one row per variant: medians, p90 tokens and seconds, overlap with the baseline."""
    variants = list(dict.fromkeys(item.variant for item in measured))
    baseline = baseline or (variants[0] if variants else None)
    header = [
        "| variant | done | failed | passages | tokens | tokens p90 | seconds | seconds p90 | overlap |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    rows: list[str] = []
    for name in variants:
        done = [item for item in measured if item.variant == name and item.status == "done"]
        failed = sum(1 for item in measured if item.variant == name and item.status != "done")
        tokens = [float(item.tokens) for item in done]
        seconds = [sum(item.seconds.values()) for item in done]
        overlap = [item.overlap[baseline] for item in done if baseline in item.overlap]
        overlap_cell = "1.00" if name == baseline and done else cell(overlap, 2)
        rows.append(
            f"| {name} | {len(done)} | {failed} | {cell([float(i.passages) for i in done])} | {cell(tokens, 0)} "
            f"| {f'{p90(tokens):.0f}' if tokens else '-'} | {cell(seconds, 2)} "
            f"| {f'{p90(seconds):.2f}' if seconds else '-'} | {overlap_cell} |"
        )
    return "\n".join([*header, *rows]) + f"\n\nOverlap: median Jaccard of selected chunks against `{baseline}`.\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.metrics", description="Metrics without an LLM.")
    parser.add_argument("--results", type=Path, required=True, help="Directory with results.jsonl.")
    parser.add_argument("--baseline", help="Variant to compare overlap against (default: the first).")
    args = parser.parse_args(argv)
    results = read_results(args.results / "results.jsonl")
    if not results:
        print(f"error: no results in {args.results / 'results.jsonl'}", file=sys.stderr)
        return 2
    measured = measure(results)
    adapter = TypeAdapter(list[ResultMetrics])
    (args.results / "metrics.json").write_bytes(adapter.dump_json(measured, indent=2) + b"\n")
    print(summarise(measured, args.baseline), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

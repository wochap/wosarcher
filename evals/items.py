"""Judged items from `items.jsonl` as Markdown, without any model call.

    python -m evals.items --results DIR [--run ID] [--failed]

One section per run (`variant · run_id`), faithfulness items first, each as
its value, passage number, claim, and passage excerpt. `--failed` keeps only
items whose value is below 1 (unreadable items included); `--run` keeps one
run. A missing items file prints nothing.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from evals.judge import JudgedItem, read_items

EXCERPT_CHARS = 300


def failed(item: JudgedItem) -> bool:
    return item.value is None or item.value < 1


def shown(value: float | None) -> str:
    return "unreadable" if value is None else f"{value:.2f}"


def render(items: Sequence[JudgedItem]) -> str:
    runs: dict[str, list[JudgedItem]] = {}
    for item in items:
        runs.setdefault(item.run_id, []).append(item)
    out: list[str] = []
    for run_id, found in runs.items():
        out.append(f"## {found[0].variant} · {run_id}\n")
        for item in sorted(found, key=lambda item: (item.kind != "faithfulness", item.index)):
            excerpt = " ".join(item.passage[:EXCERPT_CHARS].split())
            out.append(f"- {item.kind} {shown(item.value)} [{item.n}]")
            if item.claim is not None:
                out.append(f"  - claim: {item.claim}")
            out.append(f"  - passage: {excerpt}")
        out.append("")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.items", description="Judged items as Markdown.")
    parser.add_argument("--results", type=Path, required=True, help="Directory with items.jsonl.")
    parser.add_argument("--run", help="Only this fork run ID.")
    parser.add_argument("--failed", action="store_true", help="Only items whose value is below 1.")
    args = parser.parse_args(argv)
    items = [
        item
        for item in read_items(args.results / "items.jsonl")
        if (args.run is None or item.run_id == args.run) and (not args.failed or failed(item))
    ]
    if items:
        print(render(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())

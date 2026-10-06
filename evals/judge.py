"""Context precision and report faithfulness judged by the configured `llm`.

Precision is the share of selected passages rated relevant. Faithfulness is
the share of (claim, passage) pairs, one per cited number in `report.json`,
whose passage supports the claim; the claim is the sentence holding the
citation.

    python -m evals.judge --results DIR [--profile NAME] [--set KEY=VALUE ...]

Judgements go to `<DIR>/judgements.jsonl`, keyed by fork run ID; judged runs
are skipped on the next call. Only the query goes through the prompt
templates; passages and claims are sent as a separate user message.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from string import Template
from typing import cast

import httpx
from pydantic import BaseModel

import wosarcher.build as building
from evals.metrics import context
from evals.replay import read_results
from wosarcher.config import ConfigError, resolve
from wosarcher.http import ProviderError, UsageLedger
from wosarcher.models import Context, Message, Report
from wosarcher.ports import LLM
from wosarcher.stages.write import citations

PROMPT = Path(__file__).parent / "prompts" / "precision.md"
FAITHFULNESS_PROMPT = Path(__file__).parent / "prompts" / "faithfulness.md"
PASSAGE_CHARS = 1500
MAX_TOKENS = 256
MAX_PAIRS = 200
ANSWER = re.compile(r"\[[\d,\s]*\]")
SENTENCE_END = re.compile(r"[.!?\n]")


class Judgement(BaseModel):
    """One line of `judgements.jsonl`."""

    run_id: str
    parent_run_id: str
    variant: str
    selected: int
    precision: float | None
    citations: int = 0
    """(claim, passage) pairs sent to the faithfulness judge."""
    faithfulness: float | None = None


def parse_answer(text: str, count: int) -> set[int] | None:
    """Passage indexes from the first `[..]` list; indexes outside the range are ignored."""
    found = ANSWER.search(text)
    if found is None:
        return None
    try:
        indexes: object = json.loads(found.group()) if found.group().strip("[] ,") else []
    except json.JSONDecodeError:
        return None
    if not isinstance(indexes, list):
        return None
    items = cast(list[object], indexes)
    numbers = [item for item in items if type(item) is int]
    if len(numbers) != len(items):
        return None
    return {index for index in numbers if 0 <= index < count}


async def judge_result(llm: LLM, query: str, passages: Sequence[str]) -> float | None:
    """Relevant passages / selected passages; None when there is nothing to judge or the answer is unreadable."""
    if not passages:
        return None
    system = Template(PROMPT.read_text(encoding="utf-8")).substitute(query=query)
    data = "\n\n".join(f"[{index}] {text[:PASSAGE_CHARS]}" for index, text in enumerate(passages))
    messages = [Message(role="system", content=system), Message(role="user", content=data)]
    completion = await llm.complete(messages, max_tokens=MAX_TOKENS, effort="none")
    relevant = parse_answer(completion.text, len(passages))
    return None if relevant is None else len(relevant) / len(passages)


def claims(report: Report, context: Context) -> list[tuple[str, str]]:
    """One (claim, passage text) pair per cited number; the claim is the sentence holding the citation."""
    texts = {passage.n: passage.text for passage in context.passages}
    pairs: list[tuple[str, str]] = []
    previous = 0
    for start, end, numbers in citations(report.body):
        ends = [found.end() for found in SENTENCE_END.finditer(report.body, previous, start)]
        claim = " ".join(report.body[ends[-1] if ends else previous : start].split())
        pairs.extend((claim, texts[number]) for number in numbers if number in texts)
        previous = end
    return pairs


async def judge_faithfulness(llm: LLM, query: str, pairs: Sequence[tuple[str, str]]) -> float | None:
    """Supported pairs / pairs sent; None when there is nothing to judge or the answer is unreadable."""
    pairs = pairs[:MAX_PAIRS]
    if not pairs:
        return None
    system = Template(FAITHFULNESS_PROMPT.read_text(encoding="utf-8")).substitute(query=query)
    data = "\n\n".join(
        f"[{index}] claim: {claim}\npassage: {text[:PASSAGE_CHARS]}" for index, (claim, text) in enumerate(pairs)
    )
    messages = [Message(role="system", content=system), Message(role="user", content=data)]
    completion = await llm.complete(messages, max_tokens=MAX_TOKENS, effort="none")
    supported = parse_answer(completion.text, len(pairs))
    return None if supported is None else len(supported) / len(pairs)


def read_report(run_dir: Path) -> Report | None:
    path = run_dir / "report.json"
    return Report.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None


def read_judgements(path: Path) -> list[Judgement]:
    if not path.is_file():
        return []
    return [
        Judgement.model_validate_json(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()
    ]


async def judge_all(results_dir: Path, profile: str | None, overrides: list[str]) -> int:
    settings = resolve(profile, overrides, os.environ)
    path = results_dir / "judgements.jsonl"
    judged = {item.run_id for item in read_judgements(path)}
    pending = [r for r in read_results(results_dir / "results.jsonl") if r.status == "done" and r.run_id not in judged]
    ledger = UsageLedger({settings.llm.provider: settings.llm.prices})
    async with httpx.AsyncClient() as http:
        writer = building.build(settings, http, ledger).writer
        for result in pending:
            run_dir = Path(result.run_dir) if result.run_dir else None
            found = context(run_dir) if run_dir else None
            if result.run_id is None or run_dir is None or found is None:
                continue
            texts = [passage.text for passage in found.passages]
            report = read_report(run_dir)
            pairs = claims(report, found)[:MAX_PAIRS] if report else []
            try:
                precision = await judge_result(writer, found.query, texts)
                faithfulness = await judge_faithfulness(writer, found.query, pairs)
            except ProviderError as error:
                print(f"{result.variant} {result.run_id}: {' '.join(str(error).split())}", file=sys.stderr)
                precision = faithfulness = None
            judgement = Judgement(
                run_id=result.run_id,
                parent_run_id=result.parent_run_id,
                variant=result.variant,
                selected=len(texts),
                precision=precision,
                citations=len(pairs),
                faithfulness=faithfulness,
            )
            with path.open("a", encoding="utf-8") as out:
                out.write(judgement.model_dump_json() + "\n")
            print(
                f"{result.variant} {result.run_id}: precision {shown(precision)} faithfulness {shown(faithfulness)}",
                file=sys.stderr,
            )
    total = ledger.total()
    print(f"llm usage: {total.requests} requests, {total.input_tokens} input and {total.output_tokens} output tokens")
    return 0


def shown(value: float | None) -> str:
    return "missing" if value is None else f"{value:.2f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.judge", description="LLM-judged context precision and faithfulness."
    )
    parser.add_argument("--results", type=Path, required=True, help="Directory with results.jsonl.")
    parser.add_argument("--profile", help="Profile whose llm block judges.")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(judge_all(args.results, args.profile, args.set))
    except (ConfigError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

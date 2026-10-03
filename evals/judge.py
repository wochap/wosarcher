"""Context precision judged by the configured `llm`: the share of selected passages rated relevant.

    python -m evals.judge --results DIR [--profile NAME] [--set KEY=VALUE ...]

Judgements go to `<DIR>/judgements.jsonl`, keyed by fork run ID; judged runs
are skipped on the next call. Only the query goes through the prompt
template; passages are sent as a separate user message.
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

import httpx
from pydantic import BaseModel

import wosarcher.build as building
from evals.metrics import context
from evals.replay import read_results
from wosarcher.config import ConfigError, resolve
from wosarcher.http import UsageLedger
from wosarcher.models import Message
from wosarcher.ports import LLM

PROMPT = Path(__file__).parent / "prompts" / "precision.md"
PASSAGE_CHARS = 1500
MAX_TOKENS = 256
ANSWER = re.compile(r"\[[\d,\s]*\]")


class Judgement(BaseModel):
    """One line of `judgements.jsonl`."""

    run_id: str
    parent_run_id: str
    variant: str
    selected: int
    precision: float | None


def parse_answer(text: str, count: int) -> set[int] | None:
    """Passage indexes from the first `[..]` list; indexes outside the range are ignored."""
    found = ANSWER.search(text)
    if found is None:
        return None
    indexes: list[int] = json.loads(found.group()) if found.group().strip("[] ,") else []
    return {index for index in indexes if 0 <= index < count}


async def judge_result(llm: LLM, query: str, passages: Sequence[str]) -> float | None:
    """Relevant passages / selected passages; None when there is nothing to judge or the answer is unreadable."""
    if not passages:
        return None
    system = Template(PROMPT.read_text(encoding="utf-8")).substitute(query=query)
    data = "\n\n".join(f"[{index}] {text[:PASSAGE_CHARS]}" for index, text in enumerate(passages))
    messages = [Message(role="system", content=system), Message(role="user", content=data)]
    completion = await llm.complete(messages, max_tokens=MAX_TOKENS)
    relevant = parse_answer(completion.text, len(passages))
    return None if relevant is None else len(relevant) / len(passages)


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
            found = context(Path(result.run_dir)) if result.run_dir else None
            if result.run_id is None or found is None:
                continue
            texts = [passage.text for passage in found.passages]
            precision = await judge_result(writer, found.query, texts)
            judgement = Judgement(
                run_id=result.run_id,
                parent_run_id=result.parent_run_id,
                variant=result.variant,
                selected=len(texts),
                precision=precision,
            )
            with path.open("a", encoding="utf-8") as out:
                out.write(judgement.model_dump_json() + "\n")
            shown = "missing" if precision is None else f"{precision:.2f}"
            print(f"{result.variant} {result.run_id}: precision {shown}", file=sys.stderr)
    total = ledger.total()
    print(f"llm usage: {total.requests} requests, {total.input_tokens} input and {total.output_tokens} output tokens")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.judge", description="LLM-judged context precision.")
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

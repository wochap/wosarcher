"""Context precision and report faithfulness judged by the configured `llm`.

Pointwise: one yes/no call per selected passage (relevant to the query?) and
one per (claim, passage) pair, one pair per cited number in `report.json`
(does the passage support the claim, or the part the citation follows?); the
claim is the sentence holding the citation, with that citation kept as `[n]`.
Calls run concurrently at temperature 0. Precision and
faithfulness are the shares of yes over readable items; an answer whose
first word is neither yes nor no is unreadable and left out.

    python -m evals.judge --results DIR [--profile NAME] [--set KEY=VALUE ...]
                          [--samples N] [--force]

Judgements go to `<DIR>/judgements.jsonl`, keyed by fork run ID, and every
judged item to `<DIR>/items.jsonl` (read with `python -m evals.items`); judged
runs are skipped on the next call unless `--force`. `--samples N` asks every item
N times and averages. Only the query goes through the prompt templates;
passages and claims are sent as a separate user message.
"""

import argparse
import asyncio
import os
import re
import sys
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from string import Template
from typing import Literal, NamedTuple

import httpx
from pydantic import BaseModel

import wosarcher.build as building
from evals.metrics import context
from evals.replay import read_results
from wosarcher.config import ConfigError, resolve
from wosarcher.http import ProviderError, UsageLedger
from wosarcher.models import Context, Message, Report
from wosarcher.ports import LLM
from wosarcher.stages.write import CITATION, citations

PROMPT = Path(__file__).parent / "prompts" / "precision.md"
FAITHFULNESS_PROMPT = Path(__file__).parent / "prompts" / "faithfulness.md"
MAX_TOKENS = 8
MAX_PAIRS = 200
ANSWER_CHARS = 80
WORD = re.compile(r"[A-Za-z]+")
SENTENCE_BREAK = re.compile(r"[.!?](?=\s)")
"""A sentence ends at `.`, `!`, or `?` followed by whitespace, so `0.69` and `gob.pe` stay whole."""
OWN_LINE = re.compile(r"[ \t]*(?:[-*+][ \t]|\d+[.)][ \t]|\||#)")
"""List items, table rows, and headings are their own block."""
LINE_MARK = re.compile(r"^\s*(?:#+|[-*+]|\d+[.)])\s+")
TABLE_ROW = re.compile(r"[ \t]*\|")
SEPARATOR = re.compile(r"[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
"""A header separator row such as `|---|:--:|`."""
CELL_PIPE = re.compile(r"(?<!\\)\|")
EMPHASIS = re.compile(r"\*+|`+|\||(?<!\w)_+|_+(?!\w)")
SHORT_WORDS = 3
MARK = "\x00"
"""Stands in for the judged citation while the claim is cleaned."""


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
    unreadable: int = 0
    """Items (passages and pairs) whose answers were neither yes nor no."""
    samples: int = 1


class JudgedItem(BaseModel):
    """One line of `items.jsonl`: a passage (precision) or a claim pair (faithfulness) and its verdict."""

    run_id: str = ""
    variant: str = ""
    kind: Literal["precision", "faithfulness"]
    index: int
    n: int
    claim: str | None = None
    short: bool = False
    """The claim has fewer than `SHORT_WORDS` words."""
    passage: str
    value: float | None
    answer: str
    """The first sample's answer text, cut to `ANSWER_CHARS`."""


def parse_yes_no(text: str) -> float | None:
    """1.0 for yes, 0.0 for no, judged on the first word without case or punctuation; None otherwise."""
    found = WORD.search(text)
    return {"yes": 1.0, "no": 0.0}.get(found.group().lower()) if found else None


async def judge_items(
    llm: LLM, system: str, items: Sequence[str], samples: int
) -> tuple[list[float | None], list[str]]:
    """Each item asked `samples` times at once: its share of yes over readable samples (else None) and first answer."""
    calls = [
        llm.complete(
            [Message(role="system", content=system), Message(role="user", content=item)],
            max_tokens=MAX_TOKENS,
            effort="none",
            temperature=0,
        )
        for item in items
        for _ in range(samples)
    ]
    texts = [completion.text for completion in await asyncio.gather(*calls)]
    answers = [parse_yes_no(text) for text in texts]
    values: list[float | None] = []
    for index in range(len(items)):
        readable = [answer for answer in answers[index * samples : (index + 1) * samples] if answer is not None]
        values.append(sum(readable) / len(readable) if readable else None)
    return values, [text[:ANSWER_CHARS] for text in texts[::samples]]


def ratio(values: Sequence[float | None]) -> tuple[float | None, int]:
    """Mean over readable items (None when there is none) and the number of unreadable items."""
    readable = [value for value in values if value is not None]
    return (sum(readable) / len(readable) if readable else None), len(values) - len(readable)


async def judge_result(
    llm: LLM, query: str, passages: Sequence[tuple[int, str]], samples: int = 1
) -> tuple[float | None, int, list[JudgedItem]]:
    """Precision over readable (n, text) passages, unreadable count, and items; None when nothing is readable."""
    system = Template(PROMPT.read_text(encoding="utf-8")).substitute(query=query)
    sent = [text for _, text in passages]
    values, answers = await judge_items(llm, system, sent, samples)
    items = [
        JudgedItem(kind="precision", index=index, n=n, passage=text, value=value, answer=answer)
        for index, ((n, _), text, value, answer) in enumerate(zip(passages, sent, values, answers, strict=True))
    ]
    return *ratio(values), items


class Span(NamedTuple):
    """A claim's source: a sentence, a table cell with its `label`, or a whole table `row`."""

    start: int
    end: int
    label: str | None = None
    row: bool = False


def cells(line: str) -> list[tuple[int, int]]:
    """(start, end) of each cell of a table row, split on unescaped pipes, outer empties dropped."""
    bounds = [found.start() for found in CELL_PIPE.finditer(line)]
    spans = [(a + 1, b) for a, b in pairwise([-1, *bounds, len(line.rstrip())])]
    if spans and not line[spans[0][0] : spans[0][1]].strip():
        spans = spans[1:]
    if spans and not line[spans[-1][0] : spans[-1][1]].strip():
        spans = spans[:-1]
    return spans


def table(rows: list[tuple[int, str]]) -> list[Span]:
    """Spans of a table: one per body cell, labelled `row label — column header`, when a separator marks the header."""
    if len(rows) < 2 or not SEPARATOR.match(rows[1][1]):
        return [Span(start, start + len(line), row=True) for start, line in rows]
    header = [clean(rows[0][1][a:b]) for a, b in cells(rows[0][1])]
    spans = [Span(rows[0][0], rows[0][0] + len(rows[0][1]), row=True)]
    for start, line in rows[2:]:
        row = cells(line)
        label = clean(line[row[0][0] : row[0][1]]) if row else ""
        for j, (a, b) in enumerate(row):
            column = header[j] if j < len(header) else ""
            spans.append(Span(start + a, start + b, label=" — ".join(part for part in (label, column) if part)))
    return spans


def sentences(body: str) -> list[Span]:
    """Spans: blocks split at blank lines and own-line items, then after sentence ends; tables by cell."""
    spans: list[Span] = []

    def split(start: int, end: int) -> None:
        for found in SENTENCE_BREAK.finditer(body, start, end):
            spans.append(Span(start, found.end()))
            start = found.end()
        spans.append(Span(start, end))

    block: int | None = None
    rows: list[tuple[int, str]] = []
    offset = 0
    for line in body.splitlines(keepends=True):
        start, offset = offset, offset + len(line)
        if TABLE_ROW.match(line):
            rows.append((start, line))
            continue
        if rows:
            spans.extend(table(rows))
            rows = []
        if line.strip() and not OWN_LINE.match(line):
            block = start if block is None else block
            continue
        if block is not None:
            split(block, start)
            block = None
        if line.strip():
            split(start, offset)
    if rows:
        spans.extend(table(rows))
    if block is not None:
        split(block, offset)
    return spans


def clean(text: str) -> str:
    """Claim text: no citations (`MARK` stays), emphasis, heading or list marks, or table pipes; spaces collapsed."""
    text = CITATION.sub("", LINE_MARK.sub("", text))
    text = " ".join(EMPHASIS.sub(" ", text).split())
    return re.sub(r"\s+([,;:.!?])", r"\1", text).rstrip(".!?;, ")


def claim_text(text: str, span: Span) -> str:
    """The cleaned claim: a cell prefixed by its label, a row's cells joined by ` — `, or the sentence."""
    if span.row:
        return " — ".join(part for part in (clean(text[a:b]) for a, b in cells(text)) if part)
    if span.label:
        return f"{span.label}: {clean(text)}"
    return clean(text)


def claims(report: Report, context: Context) -> list[tuple[str, int, str]]:
    """One (claim, n, passage text) pair per cited number; the claim is its sentence or cell, marked `[n]`."""
    texts = {passage.n: passage.text for passage in context.passages}
    spans = sentences(report.body)
    pairs: list[tuple[str, int, str]] = []
    for start, stop, numbers in citations(report.body):
        span = next((span for span in spans if span.start <= start < span.end), Span(start, start))
        claim = claim_text(report.body[span.start : start] + MARK + report.body[stop : span.end], span)
        pairs.extend(
            (claim.replace(MARK, f"[{number}]"), number, texts[number]) for number in numbers if number in texts
        )
    return pairs


async def judge_faithfulness(
    llm: LLM, query: str, pairs: Sequence[tuple[str, int, str]], samples: int = 1
) -> tuple[float | None, int, list[JudgedItem]]:
    """Supported pairs over readable pairs, the unreadable count, and the items; None when nothing is readable."""
    system = Template(FAITHFULNESS_PROMPT.read_text(encoding="utf-8")).substitute(query=query)
    sent = list(pairs[:MAX_PAIRS])
    values, answers = await judge_items(
        llm, system, [f"claim: {claim}\npassage: {text}" for claim, _, text in sent], samples
    )
    items = [
        JudgedItem(
            kind="faithfulness",
            index=index,
            n=n,
            claim=claim,
            short=len(CITATION.sub("", claim).split()) < SHORT_WORDS,
            passage=text,
            value=value,
            answer=answer,
        )
        for index, ((claim, n, text), value, answer) in enumerate(zip(sent, values, answers, strict=True))
    ]
    return *ratio(values), items


def read_report(run_dir: Path) -> Report | None:
    path = run_dir / "report.json"
    return Report.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None


def read_judgements(path: Path) -> list[Judgement]:
    return [Judgement.model_validate_json(line) for line in lines(path)]


def read_items(path: Path) -> list[JudgedItem]:
    return [JudgedItem.model_validate_json(line) for line in lines(path)]


def lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def write_lines(path: Path, records: Sequence[BaseModel], mode: Literal["w", "a"]) -> None:
    with path.open(mode, encoding="utf-8") as out:
        out.write("".join(record.model_dump_json() + "\n" for record in records))


async def judge_all(
    results_dir: Path, profile: str | None, overrides: list[str], *, samples: int = 1, force: bool = False
) -> int:
    settings = resolve(profile, overrides, os.environ)
    path = results_dir / "judgements.jsonl"
    items_path = results_dir / "items.jsonl"
    done = [r for r in read_results(results_dir / "results.jsonl") if r.status == "done"]
    kept = read_judgements(path)
    if force:
        again = {r.run_id for r in done}
        kept = [item for item in kept if item.run_id not in again]
        write_lines(path, kept, "w")
        write_lines(items_path, [item for item in read_items(items_path) if item.run_id not in again], "w")
    judged = {item.run_id for item in kept}
    pending = [r for r in done if r.run_id not in judged]
    ledger = UsageLedger({settings.llm.provider: settings.llm.prices})
    async with httpx.AsyncClient() as http:
        writer = building.build(settings, http, ledger).writer
        for result in pending:
            run_dir = Path(result.run_dir) if result.run_dir else None
            found = context(run_dir) if run_dir else None
            if result.run_id is None or run_dir is None or found is None:
                continue
            texts = [(passage.n, passage.text) for passage in found.passages]
            report = read_report(run_dir)
            pairs = claims(report, found)[:MAX_PAIRS] if report else []
            try:
                precision, unreadable, items = await judge_result(writer, found.query, texts, samples)
                faithfulness, unread_pairs, pair_items = await judge_faithfulness(writer, found.query, pairs, samples)
                unreadable += unread_pairs
                items += pair_items
            except ProviderError as error:
                print(f"{result.variant} {result.run_id}: {' '.join(str(error).split())}", file=sys.stderr)
                precision = faithfulness = None
                unreadable = 0
                items = []
            judgement = Judgement(
                run_id=result.run_id,
                parent_run_id=result.parent_run_id,
                variant=result.variant,
                selected=len(texts),
                precision=precision,
                citations=len(pairs),
                faithfulness=faithfulness,
                unreadable=unreadable,
                samples=samples,
            )
            write_lines(path, [judgement], "a")
            key = {"run_id": result.run_id, "variant": result.variant}
            write_lines(items_path, [item.model_copy(update=key) for item in items], "a")
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
    parser.add_argument("--samples", type=int, default=1, help="Times each item is asked; answers are averaged.")
    parser.add_argument("--force", action="store_true", help="Judge again results that already have a judgement.")
    args = parser.parse_args(argv)
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    try:
        return asyncio.run(judge_all(args.results, args.profile, args.set, samples=args.samples, force=args.force))
    except (ConfigError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

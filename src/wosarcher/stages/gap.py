"""Gap: after a research round, the LLM reads a coverage table and the best passages so far and writes follow-ups.

Only the main query, the follow-up limit, and the date go through the
template; the coverage table, the queries, and the passage text go in a
delimited data block of the user message. Follow-ups are validated before
they reach a search: no URLs, a length cap, no duplicates, at most `limit`.
When none survives, the model is asked once more with the rejected queries.
"""

import json
import re
from collections.abc import Sequence
from typing import Literal, cast

from wosarcher.config import ScoreConfig
from wosarcher.models import Completion, Context, Effort, GapResult, Message, Query, Score
from wosarcher.ports import LLM
from wosarcher.prompts import load
from wosarcher.stages.plan import escape
from wosarcher.stages.score import threshold_display
from wosarcher.stages.search import MAX_SEARCH_CHARS
from wosarcher.stages.write import passage_locator

MAX_TOKENS = 768
URL = re.compile(r"https?://|www\.", re.IGNORECASE)
QUERY_ID = re.compile(r"q(\d+)")
RELATIVE = "relative scale; every query keeps its best pair, so judge by best"

Status = Literal["covered", "uncovered", "unscored"]
Rejection = Literal["empty", "too long", "URL", "duplicate"]


class GapUnreadableError(Exception):
    """The gap answer was not the expected JSON object."""


def status(scores: Sequence[Score]) -> Status:
    """`covered`, `unscored`, or `uncovered` from one query's pairs, as the score stage kept or dropped them."""
    if any((score.kept and score.display is not None) or score.dropped == "other_query" for score in scores):
        return "covered"
    if any(score.kept for score in scores):
        return "unscored"
    return "uncovered"


def scale(scorer: str, cfg: ScoreConfig) -> str:
    if scorer == "jev":
        shown = threshold_display("jev", cfg, None) or 0.0
        return f"jev (absolute 0\N{EN DASH}1 scale, kept from {shown:.2f})"
    if scorer == "passthrough":
        return "passthrough (no scores; small pages kept without ranking)"
    return f"{scorer} ({RELATIVE})"


def coverage(queries: Sequence[Query], scores: Sequence[Score], cfg: ScoreConfig) -> tuple[str, list[str]]:
    """The coverage table, one line per query in plan order, and the IDs of the `uncovered` queries."""
    by_query: dict[str, list[Score]] = {}
    for score in scores:
        by_query.setdefault(score.query_id, []).append(score)
    scorers = list(dict.fromkeys(score.scorer for score in scores))
    header = "Scorers: " + ("; ".join(scale(name, cfg) for name in scorers) if scorers else "none ran")
    lines = [header]
    uncovered: list[str] = []
    for query in queries:
        own = by_query.get(query.id, [])
        shown = [score.display for score in own if score.display is not None]
        best = f"{max(shown):.2f}" if shown else "—"
        kept = sum(score.kept for score in own)
        found = status(own)
        if found == "uncovered":
            uncovered.append(query.id)
        lines.append(f"{query.id} · {found} · best {best} · kept {kept} — {query.text}")
    return "\n".join(lines), uncovered


def messages(
    query: str, table: str, known: Sequence[Query], context: Context, *, limit: int, today: str
) -> list[Message]:
    """`known` holds the latest round's queries when that round fetched no new page, else nothing."""
    system = load("gap").substitute(query=query, limit=limit, today=today)
    titles = {source.source_id: source.title for source in context.sources}
    blocks = [f"Coverage:\n{table}"]
    if known:
        lines = "\n".join(f"- {item.id} {item.text}" for item in known)
        blocks.append(f"Round {known[0].round} found only pages fetched in earlier rounds:\n{lines}")
    entries: list[str] = []
    for passage in context.passages:
        locator = passage_locator(passage)
        label = f"[{passage.n}] {titles.get(passage.source_id, '')}" + (f" — {locator}" if locator else "")
        entries.append(f"{label}\n{passage.text}\n")
    blocks.append("Passages:\n" + "\n".join(entries))
    data = escape("\n\n".join(blocks))
    preamble = load("gap_data").template.strip()
    return [
        Message(role="system", content=system),
        Message(role="user", content=f"{preamble}\n\n<data>\n{data}\n</data>"),
    ]


def retry_message(rejected: Sequence[tuple[str, Rejection]], *, limit: int) -> Message:
    prompt = load("gap_retry").substitute(limit=limit).strip()
    lines = "\n".join(f"- {json.dumps(text, ensure_ascii=False)}: {reason}" for text, reason in rejected)
    return Message(role="user", content=f"{prompt}\n\n<data>\n{escape(lines or '- no query')}\n</data>")


def parse(answer: str) -> tuple[list[str], str]:
    """`queries` and `note` from the JSON object in the answer, ignoring other fields; raises `GapUnreadableError`."""
    first, last = answer.find("{"), answer.rfind("}")
    if first < 0 or last <= first:
        raise GapUnreadableError("gap answer had no JSON object")
    try:
        value: object = json.loads(answer[first : last + 1])
    except json.JSONDecodeError as error:
        raise GapUnreadableError(f"gap answer is not JSON: {error}") from None
    if not isinstance(value, dict):
        raise GapUnreadableError("gap answer is not a JSON object")
    data = cast(dict[str, object], value)
    found = data.get("queries", [])
    note = data.get("note", "")
    if not isinstance(found, list) or not isinstance(note, str):
        raise GapUnreadableError("gap answer has the wrong field types")
    items = cast(list[object], found)
    return [item for item in items if isinstance(item, str)], note.strip()


def rejection(text: str, seen: set[str]) -> Rejection | None:
    if not text:
        return "empty"
    if len(text) > MAX_SEARCH_CHARS:
        return "too long"
    if URL.search(text):
        return "URL"
    if text.casefold() in seen:
        return "duplicate"
    return None


def follow_ups(
    found: Sequence[str], queries: Sequence[Query], limit: int
) -> tuple[list[Query], list[tuple[str, Rejection]]]:
    """Valid, new follow-ups numbered after the highest `qN` for the next round, and the rejected ones with why."""
    seen = {item.text.strip().casefold() for item in queries}
    numbers = [int(match.group(1)) for item in queries if (match := QUERY_ID.fullmatch(item.id))]
    start = max(numbers, default=0) + 1
    next_round = max((item.round for item in queries), default=1) + 1
    kept: list[str] = []
    rejected: list[tuple[str, Rejection]] = []
    for text in (item.strip() for item in found):
        reason = rejection(text, seen)
        if reason is not None:
            rejected.append((text, reason))
            continue
        seen.add(text.casefold())
        kept.append(text)
    numbered = [Query(id=f"q{start + n}", text=text, round=next_round) for n, text in enumerate(kept[:limit])]
    return numbered, rejected


async def gap(
    query: str,
    queries: Sequence[Query],
    context: Context,
    llm: LLM,
    *,
    effort: Effort,
    scores: Sequence[Score],
    score_cfg: ScoreConfig,
    known: Sequence[Query] = (),
    limit: int,
    today: str,
) -> GapResult:
    """At most two calls: the second only when the first reply keeps no follow-up."""
    table, uncovered = coverage(queries, scores, score_cfg)
    sent = messages(query, table, known, context, limit=limit, today=today)
    completion: Completion = await llm.complete(sent, max_tokens=MAX_TOKENS, effort=effort)
    found, note = parse(completion.text)
    kept, rejected = follow_ups(found, queries, limit)
    if kept:
        return GapResult(queries=kept, note=note, uncovered=uncovered)
    retry = [*sent, Message(role="assistant", content=completion.text), retry_message(rejected, limit=limit)]
    found, second = parse((await llm.complete(retry, max_tokens=MAX_TOKENS, effort=effort)).text)
    kept, _ = follow_ups(found, queries, limit)
    return GapResult(queries=kept, note=second or note, retried=True, uncovered=uncovered)

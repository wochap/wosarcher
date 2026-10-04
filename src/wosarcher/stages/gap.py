"""Gap: after a research round, one LLM call reads the best passages so far and writes follow-up queries.

Only the main query, the follow-up limit, and the date go through the
template; the existing queries and the passage text go in a delimited data
block of the user message. Follow-ups are validated before they reach a
search: no URLs, a length cap, no duplicates, at most `limit`.
"""

import json
import re
from collections.abc import Sequence
from typing import cast

from wosarcher.models import Context, GapResult, Message, Query
from wosarcher.ports import LLM
from wosarcher.prompts import load
from wosarcher.stages.plan import escape
from wosarcher.stages.write import passage_locator

MAX_TOKENS = 768
MAX_QUERY_CHARS = 200
URL = re.compile(r"https?://|www\.", re.IGNORECASE)
QUERY_ID = re.compile(r"q(\d+)")


class GapUnreadableError(Exception):
    """The gap answer was not the expected JSON object."""


def messages(query: str, queries: Sequence[Query], context: Context, *, limit: int, today: str) -> list[Message]:
    system = load("gap").substitute(query=query, limit=limit, today=today)
    titles = {source.source_id: source.title for source in context.sources}
    asked = "\n".join(f"- {item.text}" for item in queries)
    entries: list[str] = []
    for passage in context.passages:
        locator = passage_locator(passage)
        label = f"[{passage.n}] {titles.get(passage.source_id, '')}" + (f" — {locator}" if locator else "")
        entries.append(f"{label}\n{passage.text}\n")
    data = escape(f"Queries already run:\n{asked}\n\nPassages:\n" + "\n".join(entries))
    preamble = load("gap_data").template.strip()
    return [
        Message(role="system", content=system),
        Message(role="user", content=f"{preamble}\n\n<data>\n{data}\n</data>"),
    ]


def parse(answer: str) -> tuple[list[str], str, bool]:
    """`queries`, `note`, and `stop` from the JSON object in the answer; raises `GapUnreadableError`."""
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
    stop = data.get("stop", False)
    if not isinstance(found, list) or not isinstance(note, str) or not isinstance(stop, bool):
        raise GapUnreadableError("gap answer has the wrong field types")
    items = cast(list[object], found)
    return [item for item in items if isinstance(item, str)], note.strip(), stop


def follow_ups(found: Sequence[str], queries: Sequence[Query], limit: int) -> list[Query]:
    """Valid, new follow-ups numbered after the highest `qN`, for the round after the latest."""
    seen = {item.text.strip().casefold() for item in queries}
    numbers = [int(match.group(1)) for item in queries if (match := QUERY_ID.fullmatch(item.id))]
    start = max(numbers, default=0) + 1
    next_round = max((item.round for item in queries), default=1) + 1
    kept: list[str] = []
    for text in (item.strip() for item in found):
        if not text or len(text) > MAX_QUERY_CHARS or URL.search(text) or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        kept.append(text)
    return [Query(id=f"q{start + n}", text=text, round=next_round) for n, text in enumerate(kept[:limit])]


async def gap(query: str, queries: Sequence[Query], context: Context, llm: LLM, *, limit: int, today: str) -> GapResult:
    completion = await llm.complete(messages(query, queries, context, limit=limit, today=today), max_tokens=MAX_TOKENS)
    found, note, stop = parse(completion.text)
    return GapResult(queries=follow_ups(found, queries, limit), note=note, stop=stop)

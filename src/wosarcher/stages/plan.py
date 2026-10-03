"""Plan: one LLM call turns the main query, initial hit metadata, and attachment outlines into sub-queries.

Fetched page text is never an input. Only the query and options go through
the template; hit metadata and outlines go in a separate, delimited data message.
"""

import json
from collections.abc import Sequence
from typing import cast

from wosarcher.models import Hit, Message, Plan, Query, Sources
from wosarcher.ports import LLM
from wosarcher.prompts import load

MAX_HITS = 10
MAX_TOKENS = 512
UNREADABLE = "planner answer had no query list"


def escape(text: str) -> str:
    """Keep data from opening or closing the `<data>` block."""
    return text.replace("</data", "&lt;/data").replace("<data", "&lt;data")


def messages(query: str, initial: Sequence[Hit], outlines: Sequence[str], max_sub_queries: int) -> list[Message]:
    system = load("plan").substitute(query=query, max_sub_queries=max_sub_queries)
    hits = [f"- {hit.title} — {hit.snippet}" for hit in sorted(initial, key=lambda hit: hit.rank)[:MAX_HITS]]
    blocks = ["\n".join(hits), *outlines] if hits else list(outlines)
    data = "\n\n".join(escape(block) for block in blocks)
    preamble = load("plan_data").template.strip()
    return [
        Message(role="system", content=system),
        Message(role="user", content=f"{preamble}\n\n<data>\n{data}\n</data>"),
    ]


def strings(text: str, start: str, end: str) -> list[str] | None:
    """The JSON value between the first `start` and last `end`, if it parses."""
    first, last = text.find(start), text.rfind(end)
    if first < 0 or last <= first:
        return None
    try:
        value: object = json.loads(text[first : last + 1])
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        value = cast(dict[str, object], value).get("queries")
    if not isinstance(value, list):
        return None
    items = cast(list[object], value)
    return [item for item in items if isinstance(item, str)] if all(isinstance(item, str) for item in items) else None


def parse(answer: str) -> list[str] | None:
    found = strings(answer, "{", "}")
    return found if found is not None else strings(answer, "[", "]")


def sub_queries(found: Sequence[str], query: str, limit: int) -> list[Query]:
    seen = {query.strip().casefold()}
    kept: list[str] = []
    for text in (item.strip() for item in found):
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            kept.append(text)
    return [Query(id=f"q{n}", text=text) for n, text in enumerate(kept[:limit], start=1)]


async def plan(
    query: str,
    initial: Sequence[Hit],
    outlines: Sequence[str],
    llm: LLM,
    *,
    sources: Sources,
    max_sub_queries: int,
) -> Plan:
    main = Query(id="q0", text=query)
    if sources == "files" or max_sub_queries == 0:
        return Plan(queries=[main])
    if sources == "web":
        outlines = ()
    completion = await llm.complete(messages(query, initial, outlines, max_sub_queries), max_tokens=MAX_TOKENS)
    found = parse(completion.text)
    if found is None:
        return Plan(queries=[main], warnings=[UNREADABLE])
    return Plan(queries=[main, *sub_queries(found, query, max_sub_queries)])

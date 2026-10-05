"""Plan: one LLM call turns the main query, initial hit metadata, and attachment outlines into a topic and sub-queries.

The topic line becomes `q0`: what is searched and ranked against. The user's
query stays on the request for the planner, the gap step, and the writer.

Fetched page text is never an input. Only the query and options go through
the template; hit metadata and outlines go in a separate, delimited data message.
"""

import json
from collections.abc import Sequence
from typing import cast

from wosarcher.models import Hit, Message, Plan, Query, Sources
from wosarcher.ports import LLM
from wosarcher.prompts import load
from wosarcher.stages.search import MAX_SEARCH_CHARS, cut

MAX_HITS = 10
MAX_TOKENS = 512
UNREADABLE = "planner answer had no query list"
NO_TOPIC = "planner answer had no usable topic; the query is used as the topic"


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


def json_value(text: str, start: str, end: str) -> object:
    """The JSON value between the first `start` and last `end`, or `None` if it does not parse."""
    first, last = text.find(start), text.rfind(end)
    if first < 0 or last <= first:
        return None
    try:
        return json.loads(text[first : last + 1])
    except json.JSONDecodeError:
        return None


def parse(answer: str) -> tuple[str | None, list[str]] | None:
    """The topic and sub-queries from a `{"topic", "queries"}` object or a bare list; `None` if unreadable."""
    value = json_value(answer, "{", "}")
    topic: object = None
    if isinstance(value, dict):
        data = cast(dict[str, object], value)
        topic, value = data.get("topic"), data.get("queries")
    else:
        value = json_value(answer, "[", "]")
    if not isinstance(value, list):
        return None
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        return None
    return (topic if isinstance(topic, str) else None), cast(list[str], items)


def usable_topic(topic: str | None) -> str | None:
    """The trimmed topic, or `None` when it is empty or longer than a search engine takes."""
    text = (topic or "").strip()
    return text if text and len(text) <= MAX_SEARCH_CHARS else None


def sub_queries(found: Sequence[str], seen: Sequence[str], limit: int) -> list[Query]:
    """Trimmed, non-empty sub-queries that repeat nothing in `seen` or each other, numbered from `q1`."""
    known = {text.strip().casefold() for text in seen}
    kept: list[str] = []
    for text in (item.strip() for item in found):
        if text and text.casefold() not in known:
            known.add(text.casefold())
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
    fallback = Query(id="q0", text=query if sources == "files" else cut(query))
    if sources == "files" or max_sub_queries == 0:
        return Plan(queries=[fallback])
    if sources == "web":
        outlines = ()
    completion = await llm.complete(messages(query, initial, outlines, max_sub_queries), max_tokens=MAX_TOKENS)
    found = parse(completion.text)
    if found is None:
        return Plan(queries=[fallback], warnings=[UNREADABLE])
    topic, texts = found
    usable = usable_topic(topic)
    main = fallback if usable is None else Query(id="q0", text=usable)
    queries = sub_queries(texts, [query, main.text], max_sub_queries)
    return Plan(queries=[main, *queries], warnings=[] if usable else [NO_TOPIC])

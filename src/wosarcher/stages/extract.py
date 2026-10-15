"""Extract: one LLM call per node reads the node's pages whole and returns its record and children.

Only the structure's fields, the node's name, type, and parent name, the
relation, the expand mode, the children limit, and the date go through the
template; page text goes in a delimited data block of the user message, cut
evenly to the extract budget. The reply is checked in code (`check`) before it
becomes a record.
"""

import asyncio
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from wosarcher.models import (
    Chunk,
    Effort,
    ExpandMode,
    ExtractedRecord,
    Message,
    Node,
    Page,
    Structure,
    is_http_url,
    normalise_url,
)
from wosarcher.ports import LLM
from wosarcher.prompts import load
from wosarcher.stages import noop
from wosarcher.stages.plan import escape
from wosarcher.stages.select import estimate_tokens

OUTPUT_TOKENS = 2048
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHILDREN_RULES: dict[ExpandMode, str] = {
    "links": "Take children from the links on the pages, with the URL each link shows.",
    "search": "Take children from the page text only, with url null.",
    "both": "Take children from the page text and its links; give the URL a link shows for a child, else null.",
}
NO_CHILDREN = "This entity's children are not needed: give an empty list."


class ExtractUnreadableError(Exception):
    """The reply held no readable JSON object."""


@dataclass(frozen=True)
class Child:
    name: str
    type: str
    url: str | None = None


@dataclass(frozen=True)
class NodePages:
    """A node, its parent's name, and its pages with their chunks in order."""

    node: Node
    parent_name: str | None
    pages: list[tuple[Page, list[Chunk]]]
    expandable: bool = True


@dataclass(frozen=True)
class Extracted:
    node_id: str
    record: ExtractedRecord | None = None
    """None when the call failed or the reply was unreadable."""
    children: list[Child] = field(default_factory=list[Child])
    reason: str | None = None


@dataclass(frozen=True)
class Sizing:
    context_tokens: int | None
    """`catalog.context_tokens`, or None for `auto`."""
    context_window: int
    prompt_reserve_tokens: int
    chars_per_token: float
    token_margin: float

    def estimate(self, text: str) -> int:
        return estimate_tokens(text, chars_per_token=self.chars_per_token, margin=self.token_margin)

    def chars(self, tokens: int) -> int:
        return max(math.floor(tokens * self.chars_per_token / self.token_margin), 0)

    def budget(self, system: str) -> int:
        """The configured budget, or for `auto` the room the window leaves after the reserve, output, and system."""
        if self.context_tokens is not None:
            return self.context_tokens
        room = self.context_window - self.prompt_reserve_tokens - OUTPUT_TOKENS - self.estimate(system)
        if room <= 0:
            raise ValueError(f"llm.context_window ({self.context_window}) leaves no room for the extract pages")
        return room


def generated_fields(structure: Structure) -> set[str]:
    """The slug, ref, and enum fields: filled by the crawl, never by extraction."""
    fields = (structure.slug_field, structure.ref_field, structure.enum_field)
    return {item.name for item in fields if item is not None}


def system_message(structure: Structure, item: NodePages, *, max_children: int, today: str) -> str:
    fields = [item.model_dump(exclude_defaults=True) for item in structure.fields]
    return load("extract").substitute(
        name=item.node.name,
        type=item.node.type,
        parent=item.parent_name or "none",
        fields=json.dumps(fields, ensure_ascii=False),
        relation=structure.relation,
        children_rule=CHILDREN_RULES[structure.expand] if item.expandable else NO_CHILDREN,
        max_children=max_children if item.expandable else 0,
        today=today,
    )


def page_heading(page: Page, today: str) -> str:
    source = page.source
    dated = f"fetched {today}" + (f", published {source.published}" if source.published else "")
    return f"## {source.title}\n{source.uri} ({dated})"


def page_body(page: Page, chunks: Sequence[Chunk]) -> str:
    """The page's chunks in order, or its text when it has none."""
    ordered = sorted(chunks, key=lambda piece: piece.position)
    return "\n\n".join(piece.text for piece in ordered) if ordered else page.text


def cut_evenly(blocks: Sequence[tuple[str, str]], budget: int, sizing: Sizing) -> list[str]:
    """Each `(heading, body)` joined; over budget, bodies are cut so every page gets an even share, small ones whole."""
    sizes = [sizing.estimate(f"{heading}\n\n{body}") for heading, body in blocks]
    if sum(sizes) <= budget:
        return [f"{heading}\n\n{body}" for heading, body in blocks]
    allowed = [0] * len(blocks)
    left = budget
    order = sorted(range(len(blocks)), key=lambda n: sizes[n])
    for position, n in enumerate(order):
        share = left // (len(blocks) - position)
        allowed[n] = min(sizes[n], share)
        left -= allowed[n]
    joined: list[str] = []
    for n, (heading, body) in enumerate(blocks):
        if allowed[n] >= sizes[n]:
            joined.append(f"{heading}\n\n{body}")
            continue
        room = max(sizing.chars(allowed[n]) - len(heading) - 2, 0)
        joined.append(f"{heading}\n\n{body[:room].rstrip()}")
    return joined


def messages(structure: Structure, item: NodePages, *, max_children: int, today: str, sizing: Sizing) -> list[Message]:
    system = system_message(structure, item, max_children=max_children, today=today)
    blocks = [(page_heading(page, today), page_body(page, chunks)) for page, chunks in item.pages]
    pages = cut_evenly(blocks, sizing.budget(system), sizing)
    data = escape("\n\n".join(pages))
    preamble = load("extract_data").template.strip()
    return [
        Message(role="system", content=system),
        Message(role="user", content=f"{preamble}\n\n<data>\n{data}\n</data>"),
    ]


def parse(answer: str) -> dict[str, Any]:
    first, last = answer.find("{"), answer.rfind("}")
    if first < 0 or last <= first:
        raise ExtractUnreadableError("extract reply had no JSON object")
    try:
        value: object = json.loads(answer[first : last + 1])
    except json.JSONDecodeError as error:
        raise ExtractUnreadableError(f"extract reply is not JSON: {error}") from None
    if not isinstance(value, dict):
        raise ExtractUnreadableError("extract reply is not a JSON object")
    return cast(dict[str, Any], value)


def text_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, bool | int | float):
        return str(value)
    return None


def as_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def children_of(value: object) -> list[Child]:
    found: list[Child] = []
    for raw in cast(list[object], value) if isinstance(value, list) else []:
        entry = as_dict(raw)
        name, kind, url = text_value(entry.get("name")), text_value(entry.get("type")), text_value(entry.get("url"))
        if name is None:
            continue
        found.append(Child(name=name, type=kind or "", url=url if url and is_http_url(url) else None))
    return found


def check(
    reply: dict[str, Any], structure: Structure, node: Node, page_urls: Sequence[str], *, max_children: int
) -> tuple[ExtractedRecord, list[Child]]:
    """Unknown and generated keys dropped, foreign sources unset, bad URLs, dates, and undated volatiles nulled."""
    generated = generated_fields(structure)
    given = as_dict(reply.get("record"))
    cited = as_dict(reply.get("sources"))
    own = {normalise_url(url) for url in page_urls}
    flags = [text for text in (text_value(flag) for flag in cast(list[object], reply.get("flags") or [])) if text]
    record: dict[str, str | None] = {}
    for item in structure.fields:
        if item.name in generated:
            continue
        value = text_value(given.get(item.name))
        if value is not None and item.type == "url" and not is_http_url(value):
            flags.append(f"{item.name}: not an http or https URL")
            value = None
        if value is not None and item.type == "date" and not DATE.match(value):
            flags.append(f"{item.name}: not a YYYY-MM-DD date")
            value = None
        record[item.name] = value
    for item in structure.fields:
        if item.volatile and record.get(item.name) is not None:
            dated = record.get(item.dated_by or "")
            if dated is None:
                flags.append(f"{item.name}: no dated source")
                record[item.name] = None
    sources: dict[str, str] = {}
    for name, value in record.items():
        url = text_value(cited.get(name))
        if value is None or url is None:
            continue
        if normalise_url(url) in own:
            sources[name] = url
        else:
            flags.append(f"{name}: source not among the node's pages")
    children = children_of(reply.get("children"))
    if len(children) > max_children:
        flags.append(f"children: {len(children) - max_children} beyond the limit dropped")
        children = children[:max_children]
    return ExtractedRecord(node_id=node.id, record=record, sources=sources, flags=flags), children


async def extract_one(
    item: NodePages, structure: Structure, llm: LLM, *, max_children: int, today: str, sizing: Sizing, effort: Effort
) -> Extracted:
    node = item.node
    try:
        sent = messages(structure, item, max_children=max_children, today=today, sizing=sizing)
        completion = await llm.complete(sent, max_tokens=OUTPUT_TOKENS, effort=effort)
        reply = parse(completion.text)
    except Exception as error:
        return Extracted(node_id=node.id, reason=str(error) or type(error).__name__)
    urls = [page.source.uri for page, _ in item.pages]
    if not item.expandable:
        reply = {**reply, "children": list[object]()}
    record, children = check(reply, structure, node, urls, max_children=max_children)
    return Extracted(node_id=node.id, record=record, children=children)


async def extract(
    items: Sequence[NodePages],
    structure: Structure,
    llm: LLM,
    *,
    concurrency: int,
    max_children: int,
    today: str,
    sizing: Sizing,
    effort: Effort = "none",
    on_item: Callable[[Extracted], None] = noop,
) -> list[Extracted]:
    """At most `concurrency` calls in flight; a failed call is an `Extracted` with a reason, never an exception."""
    gate = asyncio.Semaphore(concurrency)

    async def one(item: NodePages) -> Extracted:
        async with gate:
            found = await extract_one(
                item, structure, llm, max_children=max_children, today=today, sizing=sizing, effort=effort
            )
        on_item(found)
        return found

    return list(await asyncio.gather(*(one(item) for item in items)))

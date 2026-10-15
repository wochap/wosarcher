"""Draft: validate a supplied catalog structure, or derive one from the brief with one LLM call; seed the frontier.

Only the brief, the default limits, and the date go through the template; the
attachment outlines go in a separate, delimited data message. The server's
draft route calls `draft_structure` directly.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError

from wosarcher.config import CatalogConfig, catalog_structure
from wosarcher.models import Effort, Message, Node, Structure
from wosarcher.ports import LLM
from wosarcher.prompts import load
from wosarcher.stages.assemble import unique_slug
from wosarcher.stages.plan import escape, json_value

MAX_TOKENS = 4096


class DraftFailedError(Exception):
    """The draft call failed, or its reply held no valid structure; the message starts with `draft failed:`."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"draft failed: {reason}")
        self.reason = reason


@dataclass(frozen=True)
class DraftResult:
    structure: Structure
    nodes: list[Node]
    """One node per seed, at depth 0, in seed order."""
    derived: bool
    """Whether the LLM call ran."""


def validation_error(error: ValidationError) -> str:
    """The first error as `<location>: <message>`."""
    first = error.errors()[0]
    location = ".".join(str(part) for part in first["loc"])
    message = str(first["msg"]).removeprefix("Value error, ")
    return f"{location}: {message}" if location else message


def messages(brief: str, outlines: Sequence[str], catalog: CatalogConfig, today: str) -> list[Message]:
    limits = catalog.limits
    system = load("draft").substitute(
        brief=brief,
        max_depth=limits.max_depth,
        max_nodes=limits.max_nodes,
        pages_per_node=limits.pages_per_node,
        today=today,
    )
    data = "\n\n".join(escape(outline) for outline in outlines)
    preamble = load("draft_data").template.strip()
    return [
        Message(role="system", content=system),
        Message(role="user", content=f"{preamble}\n\n<data>\n{data}\n</data>"),
    ]


def parse(answer: str, catalog: CatalogConfig) -> Structure:
    """The structure in the reply with the `catalog` block's defaults for absent limits and expand mode."""
    value = json_value(answer, "{", "}")
    if not isinstance(value, dict):
        raise DraftFailedError("the reply holds no JSON object")
    try:
        return catalog_structure(cast(dict[str, Any], value), catalog)
    except ValidationError as error:
        raise DraftFailedError(validation_error(error)) from None


async def draft_structure(
    brief: str,
    outlines: Sequence[str],
    llm: LLM,
    *,
    today: str,
    catalog: CatalogConfig | None = None,
    effort: Effort = "none",
) -> Structure:
    """One LLM call that derives a structure from the brief; raises `DraftFailedError` on a failed call or bad reply."""
    catalog = catalog or CatalogConfig()
    try:
        completion = await llm.complete(messages(brief, outlines, catalog, today), max_tokens=MAX_TOKENS, effort=effort)
    except Exception as error:
        raise DraftFailedError(str(error) or type(error).__name__) from None
    return parse(completion.text, catalog)


def checked(structure: Structure | dict[str, Any], catalog: CatalogConfig) -> Structure:
    """A supplied structure validated, with the block's defaults for keys it leaves unset."""
    try:
        return catalog_structure(structure, catalog)
    except ValidationError as error:
        raise ValueError(f"invalid structure: {validation_error(error)}") from None


def seed_nodes(structure: Structure) -> list[Node]:
    taken: set[str] = set()
    return [
        Node(id=unique_slug(seed.name, taken), name=seed.name, type=seed.type, url=seed.url, found_by="seed")
        for seed in structure.seeds
    ]


async def draft(
    brief: str,
    structure: Structure | None,
    outlines: Sequence[str],
    llm: LLM,
    *,
    catalog: CatalogConfig,
    today: str,
    effort: Effort = "none",
) -> DraftResult:
    """With a structure: validate it, no call. Without: derive one. Either way, the seed nodes."""
    derived = structure is None
    found = (
        await draft_structure(brief, outlines, llm, today=today, catalog=catalog, effort=effort)
        if structure is None
        else checked(structure, catalog)
    )
    return DraftResult(structure=found, nodes=seed_nodes(found), derived=derived)

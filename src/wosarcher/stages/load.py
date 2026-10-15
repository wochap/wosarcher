"""Load: attachment bytes become file pages; outlines summarise them for the planner.

No page cap: attachments are bounded by `attach.max_bytes`, and cutting a
document the user asked about would silently lose answers.
"""

import json
import re
from collections.abc import Sequence
from typing import Literal, cast

from wosarcher.models import Attachment, LoadResult, Page, Skipped, Source, file_source_id
from wosarcher.stages.chunk import clean, sections

PDF_INGEST = re.compile(r"<!--\s*page:\s*(.+?)\s*-->")
OUTLINE_LINES = 2
JSON_MAX_DEPTH = 6
NAME_KEYS = ("name", "title", "id", "label")

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None


def title_of(text: str, name: str) -> str:
    return next((section.path[0] for section in sections(text) if section.level == 1), name)


def _compact(value: Json) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _scalar(value: Json) -> str:
    return value if isinstance(value, str) else _compact(value)


def _item_title(item: Json, index: int) -> str:
    if isinstance(item, dict):
        for key in NAME_KEYS:
            found = item.get(key)
            if isinstance(found, str):
                return found
    return f"Item {index}"


def _is_objects(value: Json) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _items(value: list[Json], level: int, depth: int, indent: str, out: list[str]) -> None:
    """An array inside a section: objects as deeper sections, anything else as bullets."""
    if _is_objects(value):
        if level >= JSON_MAX_DEPTH or depth >= JSON_MAX_DEPTH:
            out.append(indent + _compact(value))
            return
        for index, item in enumerate(value, 1):
            out.extend(["", f"{'#' * (level + 1)} {_item_title(item, index)}", ""])
            _body(item, level + 1, depth + 1, "", out)
        return
    for item in value:
        out.append(f"{indent}- {_scalar(item) if not isinstance(item, (dict, list)) else _compact(item)}")


def _field(key: str, value: Json, level: int, depth: int, indent: str, out: list[str]) -> None:
    if not isinstance(value, (dict, list)):
        out.append(f"{indent}{key}: {_scalar(value)}")
    elif depth >= JSON_MAX_DEPTH:
        out.append(f"{indent}{key}: {_compact(value)}")
    elif isinstance(value, dict):
        out.append(f"{indent}{key}:")
        for sub_key, sub_value in value.items():
            _field(sub_key, sub_value, level, depth + 1, indent + "  ", out)
    else:
        out.append(f"{indent}{key}:")
        _items(value, level, depth + 1, indent, out)


def _body(value: Json, level: int, depth: int, indent: str, out: list[str]) -> None:
    """The lines of one section whose content is `value`."""
    if isinstance(value, dict):
        for key, sub_value in value.items():
            _field(key, sub_value, level, depth, indent, out)
    elif isinstance(value, list):
        _items(value, level, depth, indent, out)
    else:
        out.append(indent + _scalar(value))


def render_json(value: Json) -> str:
    """Markdown for a parsed JSON document: a `##` section per top-level key or item."""
    out: list[str] = []
    if isinstance(value, dict):
        for key, sub_value in value.items():
            out.extend(["", f"## {key}", ""])
            _body(sub_value, 2, 1, "", out)
    elif isinstance(value, list):
        for index, item in enumerate(value, 1):
            out.extend(["", f"## {_item_title(item, index)}", ""])
            _body(item, 2, 1, "", out)
    else:
        out.append(_scalar(value))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def load(attachments: Sequence[Attachment]) -> LoadResult:
    pages: list[Page] = []
    skipped: list[Skipped] = []
    first: dict[str, str] = {}
    for attachment in attachments:
        source_id = file_source_id(attachment.data)
        if source_id in first:
            skipped.append(Skipped(item=attachment.name, reason=f"duplicate of {first[source_id]}"))
            continue
        text = attachment.data.decode("utf-8", errors="replace")
        page_format: Literal["markdown", "pdf-ingest", "json"]
        if attachment.name.lower().endswith(".json"):
            try:
                text = render_json(cast(Json, json.loads(text)))
            except json.JSONDecodeError as error:
                skipped.append(Skipped(item=attachment.name, reason=f"invalid JSON: {error}"))
                continue
            title, page_format = attachment.name, "json"
        else:
            title = title_of(text, attachment.name)
            page_format = "pdf-ingest" if PDF_INGEST.search(text) else "markdown"
        first[source_id] = attachment.name
        source = Source(source_id=source_id, kind="file", uri=attachment.name, title=title)
        pages.append(Page(source=source, text=text, format=page_format))
    return LoadResult(pages=pages, skipped=skipped)


def outline(page: Page, *, max_chars: int = 2000) -> str:
    """Title, each heading with its level, and the first two non-empty lines under it."""
    parts = [f"Title: {page.source.title}"]
    for section in sections(page.text):
        if section.level:
            parts.append(f"{'#' * section.level} {section.path[-1]}")
        lines = [line.strip() for line in clean(section.text).splitlines() if line.strip()]
        parts.extend(lines[:OUTLINE_LINES])
    return "\n".join(parts)[:max_chars]

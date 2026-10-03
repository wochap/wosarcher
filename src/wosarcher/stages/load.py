"""Load: attachment bytes become file pages; outlines summarise them for the planner.

No page cap: attachments are bounded by `attach.max_bytes`, and cutting a
document the user asked about would silently lose answers.
"""

import re
from collections.abc import Sequence

from wosarcher.models import Attachment, LoadResult, Page, Skipped, Source, file_source_id
from wosarcher.stages.chunk import clean, sections

PDF_INGEST = re.compile(r"<!--\s*page:\s*(.+?)\s*-->")
OUTLINE_LINES = 2


def title_of(text: str, name: str) -> str:
    return next((section.path[0] for section in sections(text) if section.level == 1), name)


def load(attachments: Sequence[Attachment]) -> LoadResult:
    pages: list[Page] = []
    skipped: list[Skipped] = []
    first: dict[str, str] = {}
    for attachment in attachments:
        source_id = file_source_id(attachment.data)
        if source_id in first:
            skipped.append(Skipped(item=attachment.name, reason=f"duplicate of {first[source_id]}"))
            continue
        first[source_id] = attachment.name
        text = attachment.data.decode("utf-8", errors="replace")
        source = Source(source_id=source_id, kind="file", uri=attachment.name, title=title_of(text, attachment.name))
        page_format = "pdf-ingest" if PDF_INGEST.search(text) else "markdown"
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

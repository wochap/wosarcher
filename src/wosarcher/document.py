"""The Markdown that report export converts: title, date and run ID, the question, then the report.

Pure: no I/O. The converter reads it with raw HTML off, so code-made `<sup>` markers become `^n^`.
"""

import re

from wosarcher.models import Report, RunRecord

TITLE_MAX_CHARS = 120
LEADING_HEADING = re.compile(r"\A\s*# +(.+?)[ \t#]*(?:\n|\Z)")
SUPERSCRIPT = re.compile(r"<sup>([0-9]+(?:,[0-9]+)*)</sup>")
EMPHASIS = re.compile(r"(\*{1,3}|_{1,3})(\S(?:.*?\S)?)\1")


def plain(line: str) -> str:
    """`line` without Markdown emphasis markers: `**bold**` -> `bold`."""
    return EMPHASIS.sub(r"\2", line).strip()


def cut(text: str, limit: int = TITLE_MAX_CHARS) -> str:
    """`text` cut at a word boundary to at most `limit` characters, `…` included, when longer."""
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    space = head.rfind(" ")
    return (head[:space] if space > 0 else head).rstrip() + "…"


def query_title(query: str) -> str:
    first = next((line for line in query.splitlines() if line.strip()), "")
    return cut(plain(first))


def split_title(markdown: str) -> tuple[str | None, str]:
    """The report's own level-1 heading, when it starts with one, and the text after it."""
    match = LEADING_HEADING.match(markdown)
    if match is None:
        return None, markdown
    return match.group(1).strip(), markdown[match.end() :].lstrip("\n")


def quoted(text: str) -> str:
    return "\n".join(f"> {line}".rstrip() for line in text.strip().splitlines())


def document(record: RunRecord, report: Report) -> str:
    """Export Markdown for `report`, the finished write stage of the run `record`."""
    query = record.request.query.strip()
    own, body = split_title(report.markdown)
    title = own or query_title(query)
    parts = [f"# {title}", f"{record.created_at:%Y-%m-%d} · {record.run_id}"]
    if query != title:
        parts += ["## Question", quoted(query)]
    parts.append(SUPERSCRIPT.sub(r"^\1^", body).strip())
    return "\n\n".join(parts) + "\n"

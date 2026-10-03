"""Chunk: split pages by markdown headings, then by size, into cleaned, citable chunks.

pdf-ingest anchors (`<!-- page: … -->`, `<!-- a: … -->`) are swapped for
private markers before cleaning, so their offsets survive it exactly; the
markers become `page_id`/`block_ids` and are removed from the text.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256

from markdown_it import MarkdownIt

from wosarcher.models import Chunk, ChunkResult, Page, chunk_id

ANCHOR = re.compile(r"<!--\s*(page|a):\s*(.+?)\s*-->")
MARKER = re.compile("\ue000(\\d+)\ue001")

# Applied in order to every section.
CLEANING = [
    (re.compile(r"<!--.*?-->", re.DOTALL), ""),
    (re.compile(r"<img\b[^>]*>", re.IGNORECASE), ""),
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),
    (re.compile(r"<[a-zA-Z][a-zA-Z0-9+.-]*:[^>\s]*>"), ""),
    (re.compile(r"[ \t]+"), " "),
    (re.compile(r"\n{3,}"), "\n\n"),
]


@dataclass(frozen=True)
class Section:
    level: int  # heading level, 0 before the first heading
    path: tuple[str, ...]
    text: str  # body without the heading line


def sections(text: str) -> list[Section]:
    """Cut text at top-level headings; fenced code is one token, so headings inside it never split."""
    lines = text.splitlines()
    tokens = MarkdownIt("commonmark").parse(text)
    found: list[Section] = []
    stack: list[tuple[int, str]] = []
    level, start = 0, 0
    for n, token in enumerate(tokens):
        if token.type != "heading_open" or token.level != 0 or token.map is None:
            continue
        found.append(Section(level, tuple(title for _, title in stack), "\n".join(lines[start : token.map[0]])))
        level = int(token.tag[1])
        stack = [(depth, title) for depth, title in stack if depth < level] + [(level, tokens[n + 1].content.strip())]
        start = token.map[1]
    found.append(Section(level, tuple(title for _, title in stack), "\n".join(lines[start:])))
    return [section for section in found if section.level or section.text.strip()]


def clean(text: str) -> str:
    for pattern, replacement in CLEANING:
        text = pattern.sub(replacement, text)
    return text.strip()


def windows(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    """(start, end) spans of at most `size` characters, cut at a boundary in the window's second half."""
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            spans.append((start, len(text)))
            break
        half = start + size // 2
        for separator in ("\n\n", "\n", " "):
            found = text.rfind(separator, half, end)
            if found > start:
                end = found
                break
        spans.append((start, end))
        following = max(end - overlap, start + 1)
        while following < end and not (text[following - 1].isspace() and not text[following].isspace()):
            following += 1
        start = following
    return spans


def normalised(text: str) -> str:
    return re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", text).lower()).strip()


def mark_anchors(text: str, anchors: list[tuple[str, str]]) -> str:
    """Replace each anchor with a marker holding its index in `anchors`, which collects (kind, value)."""

    def replace(match: re.Match[str]) -> str:
        anchors.append((match.group(1), match.group(2)))
        return f"\ue000{len(anchors) - 1}\ue001"

    return ANCHOR.sub(replace, text)


def page_chunks(page: Page, size: int, overlap: int) -> list[Chunk]:
    anchors: list[tuple[str, str]] = []
    chunks: list[Chunk] = []
    page_id: str | None = None
    for section in sections(page.text):
        body = section.text
        if page.format == "pdf-ingest":
            body = mark_anchors(body, anchors)
        body = clean(body)
        markers = [(match.start(), anchors[int(match.group(1))]) for match in MARKER.finditer(body)]
        for start, end in windows(body, size, overlap):
            in_effect = [value for offset, (kind, value) in markers if kind == "page" and offset <= start]
            current = in_effect[-1] if in_effect else page_id
            blocks = [value for offset, (kind, value) in markers if kind == "a" and start <= offset < end]
            text = clean(MARKER.sub("", body[start:end]))
            if text:
                position = len(chunks)
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id(page.source.source_id, position, text),
                        source_id=page.source.source_id,
                        position=position,
                        text=text,
                        heading_path=list(section.path),
                        page_id=current,
                        block_ids=blocks,
                    )
                )
        pages = [value for _, (kind, value) in markers if kind == "page"]
        page_id = pages[-1] if pages else page_id
    return chunks


def chunk(pages: Sequence[Page], *, size: int, overlap: int) -> ChunkResult:
    seen: set[str] = set()
    kept: list[Chunk] = []
    duplicates = 0
    for page in pages:
        for item in page_chunks(page, size, overlap):
            key = sha256(normalised(item.text).encode("utf-8")).hexdigest()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            kept.append(item)
    return ChunkResult(chunks=kept, duplicates=duplicates)

"""Chunk: split pages by markdown headings, drop boilerplate, merge short sections, then split by size.

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

# Boilerplate: a web-page section that is mostly links, or short with no sentence punctuation.
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL = re.compile(r"<?https?://[^\s>)]+>?")
LINK_SHARE = 0.5
MIN_LINKS = 2
SHORT_WORDS = 12
SENTENCE_PUNCTUATION = set(".?!;:")
LIST_ITEM = re.compile(r"\s*(?:[-*+]|\d+[.)])\s")

# Scoring text: caps on the title and the whole context line.
TITLE_CHARS = 120
CONTEXT_CHARS = 300

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


def boilerplate(raw: str) -> bool:
    """True for raw section markdown made mostly of two or more links, or a few unpunctuated words, not a list."""
    linked = 0
    rest = IMAGE.sub(" ", re.sub(r"<!--.*?-->", " ", raw, flags=re.DOTALL))
    texts = LINK.findall(rest)
    linked += sum(len("".join(text.split())) for text in texts)
    rest = LINK.sub(" ", rest)
    urls = URL.findall(rest)
    linked += sum(len(url) for url in urls)
    rest = URL.sub(" ", rest)
    other = len("".join(rest.split()))
    if not linked + other:
        return False
    if len(texts) + len(urls) >= MIN_LINKS and linked / (linked + other) >= LINK_SHARE:
        return True
    if all(LIST_ITEM.match(line) for line in raw.splitlines() if line.strip()):
        return False  # a short list is content, such as a requirement; menus fail the link test above
    visible = " ".join([*texts, rest])
    return len(visible.split()) <= SHORT_WORDS and not SENTENCE_PUNCTUATION & set(URL.sub(" ", visible))


def drop_boilerplate(found: list[Section]) -> tuple[list[Section], int]:
    """Sections without boilerplate and the number dropped; a page keeps its longest section if all are."""
    flagged = [bool(clean(section.text)) and boilerplate(section.text) for section in found]
    if all(flagged) and found:
        longest = max(range(len(found)), key=lambda n: len(clean(found[n].text)))
        flagged[longest] = False
    kept = [section for section, flag in zip(found, flagged, strict=True) if not flag]
    return kept, sum(flagged)


def windows(text: str, size: int, overlap: int, min_chars: int = 0) -> list[tuple[int, int]]:
    """(start, end) spans of at most `size` characters, cut at a boundary in the window's second half.

    A cut that would leave less than `min_chars` moves earlier so the last span keeps `min_chars`.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            spans.append((start, len(text)))
            break
        if len(text) - end < min_chars:
            end = max(len(text) - min_chars, start + 1)
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


@dataclass(frozen=True)
class Part:
    path: tuple[str, ...]
    body: str  # cleaned text, still holding anchor markers


def common_path(paths: Sequence[tuple[str, ...]]) -> tuple[str, ...]:
    common = paths[0]
    for path in paths[1:]:
        n = 0
        while n < min(len(common), len(path)) and common[n] == path[n]:
            n += 1
        common = common[:n]
    return common


def joined(group: Sequence[Part]) -> Part:
    """One part from merged parts: the shared heading path, and every heading below it as a line, once."""
    path = common_path([part.path for part in group])
    if not any(part.body for part in group):
        return Part(path, "")
    lines: list[str] = []
    previous = path
    for part in group:
        shared = len(common_path([previous, part.path]))
        lines.extend(part.path[max(shared, len(path)) :])
        if part.body:
            lines.append(part.body)
        previous = part.path
    return Part(path, "\n\n".join(lines))


def length(group: Sequence[Part]) -> int:
    return len(MARKER.sub("", joined(group).body))


def merged(parts: list[Part], size: int, min_chars: int) -> list[Part]:
    """Greedy page-order merge: grow a group below `min_chars` while it fits `size`; a short tail joins backwards."""
    if not min_chars:
        return parts
    groups: list[list[Part]] = []
    for part in parts:
        current = groups[-1] if groups else None
        if current and (not current[-1].body or (length(current) < min_chars and length([*current, part]) <= size)):
            current.append(part)
        else:
            groups.append([part])
    if len(groups) > 1 and length(groups[-1]) < min_chars and length(groups[-2] + groups[-1]) <= size:
        groups[-2:] = [groups[-2] + groups[-1]]
    return [joined(group) for group in groups]


def page_chunks(page: Page, size: int, overlap: int, min_chars: int) -> tuple[list[Chunk], int]:
    """Chunks of one page and the number of sections dropped as boilerplate."""
    anchors: list[tuple[str, str]] = []
    chunks: list[Chunk] = []
    page_id: str | None = None
    found = sections(page.text)
    dropped = 0
    if page.source.kind == "web":
        found, dropped = drop_boilerplate(found)
    parts: list[Part] = []
    for section in found:
        body = section.text
        if page.format == "pdf-ingest":
            body = mark_anchors(body, anchors)
        parts.append(Part(section.path, clean(body)))
    for part in merged(parts, size, min_chars):
        body = part.body
        markers = [(match.start(), anchors[int(match.group(1))]) for match in MARKER.finditer(body)]
        for start, end in windows(body, size, overlap, min_chars):
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
                        heading_path=list(part.path),
                        page_id=current,
                        block_ids=blocks,
                    )
                )
        pages = [value for _, (kind, value) in markers if kind == "page"]
        page_id = pages[-1] if pages else page_id
    return chunks, dropped


def cut(text: str, limit: int) -> str:
    """`text` cut to `limit` characters, at the last word boundary when one exists."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    word_end = head.rfind(" ")
    return (head[:word_end] if word_end > 0 else head).rstrip()


def scoring_text(title: str, heading_path: Sequence[str], text: str) -> str:
    """The text rankers and scorers see: `title > h1 > h2`, an empty line, then the chunk text."""
    parts = [part for part in (cut(title.strip(), TITLE_CHARS), *(h.strip() for h in heading_path)) if part]
    if not parts:
        return text
    return f"{cut(' > '.join(parts), CONTEXT_CHARS)}\n\n{text}"


def text_hash(text: str) -> str:
    return sha256(normalised(text).encode("utf-8")).hexdigest()


def chunk(
    pages: Sequence[Page], *, size: int, overlap: int, min_chars: int, existing: Sequence[Chunk] = ()
) -> ChunkResult:
    """Chunks of `pages`, without near-duplicates of each other or of `existing` (earlier rounds' chunks)."""
    seen = {text_hash(item.text) for item in existing}
    kept: list[Chunk] = []
    duplicates = boilerplate_count = 0
    for page in pages:
        found, dropped = page_chunks(page, size, overlap, min_chars)
        boilerplate_count += dropped
        for item in found:
            key = text_hash(item.text)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            kept.append(item)
    return ChunkResult(chunks=kept, duplicates=duplicates, boilerplate=boilerplate_count)

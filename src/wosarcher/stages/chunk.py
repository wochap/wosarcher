"""Chunk: split pages by markdown headings, drop boilerplate blocks, merge short sections, then split by size.

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

# Boilerplate: a web-page block that is mostly links, has no sentence punctuation, or is a rail of short lines.
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# Link text may hold one image; the target, of any scheme, may hold one level of parentheses.
LINK = re.compile(r"\[((?:[^\[\]]|!\[[^\]]*\]\([^)]*\))*)\]\((?:[^()]|\([^()]*\))*\)")
URL = re.compile(r"<?https?://[^\s>)]+>?")
LINK_SHARE = 0.5
MIN_LINKS = 2
PUNCTUATION_END = re.compile(r"[.?!;:](?=\s|$)")
CLOCK = re.compile(r"(?<=\d):(?=\d)")
RAIL_LINES = 5
RAIL_SHARE = 0.8
RAIL_WORDS = 4
LIST_ITEM = re.compile(r"\s*(?:[-*+]|\d+[.)])\s")
FENCE = re.compile(r"\s*(?:```|~~~)")

# Scoring text: caps on the title and the whole context line.
TITLE_CHARS = 120
CONTEXT_CHARS = 300

# Applied in order to every section.
CLEANING = [
    (re.compile(r"<!--.*?-->", re.DOTALL), ""),
    (re.compile(r"<img\b[^>]*>", re.IGNORECASE), ""),
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),
    (LINK, r"\1"),
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
    """True for a raw markdown block made mostly of links (or one bare link), with no sentence punctuation, or a rail.

    Lists, tables, and fenced code are content even without punctuation; menus that are lists fail the link test.
    """
    linked = 0
    raw = IMAGE.sub(" ", re.sub(r"<!--.*?-->", " ", raw, flags=re.DOTALL))
    rest = raw
    texts = LINK.findall(rest)
    linked += sum(len("".join(text.split())) for text in texts)
    rest = LINK.sub(" ", rest)
    urls = URL.findall(rest)
    linked += sum(len(url) for url in urls)
    rest = URL.sub(" ", rest)
    other = len("".join(rest.split()))
    if not linked + other:
        return False
    links = len(texts) + len(urls)
    if (links >= MIN_LINKS and linked / (linked + other) >= LINK_SHARE) or (links == 1 and not other):
        return True
    lines = [line for line in raw.splitlines() if line.strip()]
    is_list = all(LIST_ITEM.match(line) for line in lines)
    is_table = all(line.lstrip().startswith("|") for line in lines)
    is_code = bool(FENCE.match(raw.lstrip("\n")))
    if is_list or is_table or is_code:
        return False
    visible = [unpunctuated_words(line) for line in lines]
    if all(words is not None for words in visible):
        return True
    rail = sum(1 for words in visible if words is not None and words <= RAIL_WORDS)
    return len(lines) >= RAIL_LINES and rail / len(lines) >= RAIL_SHARE


def unpunctuated_words(line: str) -> int | None:
    """Word count of a line's visible text, or None when it has sentence punctuation outside URLs."""
    visible = CLOCK.sub(" ", URL.sub(" ", LINK.sub(r" \1 ", line)))
    return None if PUNCTUATION_END.search(visible) else len(visible.split())


def kind(block: str) -> str:
    """`list` or `table` when every non-empty line is a list item or a table row, else `text`."""
    lines = [line for line in block.splitlines() if line.strip()]
    if all(LIST_ITEM.match(line) for line in lines):
        return "list"
    if all(line.lstrip().startswith("|") for line in lines):
        return "table"
    return "text"


def blocks(text: str) -> list[str]:
    """Text between blank lines; a fenced code block, and a run of list or table blocks, stay one block."""
    found: list[str] = []
    current: list[str] = []
    fenced = False
    for line in [*text.splitlines(), ""]:
        if FENCE.match(line):
            fenced = not fenced
        if line.strip() or fenced:
            current.append(line)
            continue
        if current:
            block = "\n".join(current)
            if found and kind(block) != "text" and kind(block) == kind(found[-1]):
                found[-1] += "\n\n" + block
            else:
                found.append(block)
            current = []
    return found


def drop_boilerplate(found: list[Section]) -> tuple[list[Section], int]:
    """Sections without boilerplate blocks and the number of blocks dropped; a page keeps its longest block if all are.

    A section that had text and loses every block is dropped.
    """
    split = [blocks(section.text) for section in found]
    flags = [[bool(clean(block)) and boilerplate(block) for block in parts] for parts in split]
    texted = [(n, m) for n, parts in enumerate(split) for m, block in enumerate(parts) if clean(block)]
    if texted and all(flags[n][m] for n, m in texted):
        n, m = max(texted, key=lambda key: len(clean(split[key[0]][key[1]])))
        flags[n][m] = False
    kept: list[Section] = []
    for section, parts, flagged in zip(found, split, flags, strict=True):
        rest = [block for block, flag in zip(parts, flagged, strict=True) if not flag]
        if rest or not any(flagged):
            kept.append(Section(section.level, section.path, "\n\n".join(rest)))
    return kept, sum(map(sum, flags))


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
    """Chunks of one page and the number of blocks dropped as boilerplate."""
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


def text_for(context: str, title: str, heading_path: Sequence[str], text: str) -> str:
    """The scoring text under `prefilter.context`: `header` adds the context line, `body` is the text alone."""
    return scoring_text(title, heading_path, text) if context == "header" else text


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

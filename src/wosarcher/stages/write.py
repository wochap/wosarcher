"""Write: one streamed LLM call answers the query from the selected passages; code renders citations and references.

Only the query and options go through the templates; passage titles and
text go in a delimited data block of the user message, before the task.
"""

import re
from collections.abc import Callable
from pathlib import PurePosixPath
from urllib.parse import urlparse

from wosarcher.models import Context, Message, Passage, Reference, Report, Source, WritingOptions
from wosarcher.ports import LLM
from wosarcher.prompts import load, tones
from wosarcher.stages.select import output_tokens

CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\](?!\()")
YEAR = re.compile(r"\d{4}")
NO_CITATIONS = "report cites no passage"
HEADING_SEPARATOR = " \u203a "
"""Joins a heading path (single right-pointing angle quotation mark)."""


def noop(_: str) -> None:
    pass


def escape(text: str) -> str:
    """Keep data from opening or closing the `<passages>` block."""
    return text.replace("</passages", "&lt;/passages").replace("<passages", "&lt;passages")


def passage_locator(passage: Passage) -> str:
    """Page ID for pdf-ingest passages, else the heading path."""
    return f"p. {passage.page_id}" if passage.page_id else HEADING_SEPARATOR.join(passage.heading_path)


def passage_entry(passage: Passage, title: str) -> str:
    locator = passage_locator(passage)
    label = f"[{passage.n}] {title}" + (f" — {locator}" if locator else "")
    return f"{escape(label)}\n{escape(passage.text)}\n"


def messages(context: Context, options: WritingOptions, tone_description: str) -> list[Message]:
    system = load("write").substitute(
        query=context.query,
        tone=options.tone.lower(),
        tone_description=tone_description,
        tone_instructions=options.tone_instructions,
        words=options.words,
        language=options.language,
    )
    titles = {source.source_id: source.title for source in context.sources}
    entries = "\n".join(passage_entry(passage, titles.get(passage.source_id, "")) for passage in context.passages)
    preamble = load("passages").template.strip()
    task = load("write_task").substitute(query=context.query, words=options.words, language=options.language)
    return [
        Message(role="system", content=system),
        Message(role="user", content=f"{preamble}\n\n<passages>\n{entries}</passages>\n\n{task}"),
    ]


def citations(body: str) -> list[tuple[int, int, list[int]]]:
    """Each citation group as (start, end, numbers); `[1](url)` links are not citations."""
    return [
        (match.start(), match.end(), [int(number) for number in match.group(1).split(",")])
        for match in CITATION.finditer(body)
    ]


def site(source: Source) -> str:
    """Web host without `www.`, or the file name."""
    if source.kind == "file":
        return PurePosixPath(source.uri).name
    host = urlparse(source.uri).hostname or source.uri
    return host.removeprefix("www.")


def year(source: Source) -> str:
    found = YEAR.search(source.published or "")
    return found.group() if found else "n.d."


def end(text: str) -> str:
    """`text` ending in one period: `n.d.` stays `n.d.`."""
    return text if text.endswith(".") else text + "."


def author_year(numbers: list[int], passages: dict[int, Passage], sources: dict[str, Source]) -> str:
    source_ids = list(dict.fromkeys(passages[n].source_id for n in numbers))
    parts = [f"{source.author or site(source)}, {year(source)}" for source in (sources[sid] for sid in source_ids)]
    return "(" + "; ".join(parts) + ")"


def marker(
    numbers: list[int], options: WritingOptions, passages: dict[int, Passage], sources: dict[str, Source]
) -> str:
    if options.citation_marker == "superscript":
        return "<sup>" + ",".join(map(str, numbers)) + "</sup>"
    if options.citation_marker == "author-year":
        return author_year(numbers, passages, sources)
    return "[" + ", ".join(map(str, numbers)) + "]"


def apa(source: Source, _: int) -> str:
    head = (
        f"{source.author} ({year(source)}). *{source.title}*."
        if source.author
        else f"*{source.title}* ({year(source)})."
    )
    return f"{head} {site(source)}" + (f". {source.uri}" if source.kind == "web" else "")


def mla(source: Source, _: int) -> str:
    author = f"{source.author}. " if source.author else ""
    url = f", {source.uri}" if source.kind == "web" else ""
    return end(f'{author}"{source.title}." *{site(source)}*, {year(source)}{url}')


def chicago(source: Source, _: int) -> str:
    author = f"{source.author}. " if source.author else ""
    url = f" {source.uri}." if source.kind == "web" else ""
    return end(f'{author}"{source.title}." {site(source)}. {year(source)}') + url


def ieee(source: Source, k: int) -> str:
    author = f"{source.author}, " if source.author else ""
    url = f" [Online]. Available: {source.uri}" if source.kind == "web" else ""
    return end(f'[{k}] {author}"{source.title}," {site(source)}, {year(source)}') + url


STYLES: dict[str, Callable[[Source, int], str]] = {"APA": apa, "MLA": mla, "Chicago": chicago, "IEEE": ieee}


def style(name: str) -> Callable[[Source, int], str]:
    found = {key.lower(): value for key, value in STYLES.items()}.get(name.lower())
    if found is None:
        raise ValueError(f"unknown reference style '{name}' (known: {', '.join(STYLES)})")
    return found


def tone_description(name: str) -> str:
    known = tones()
    if name.lower() not in known:
        raise ValueError(f"unknown tone '{name}' (known: {', '.join(known)})")
    return known[name.lower()]


def reference_locator(passage: Passage) -> str:
    if passage.page_id:
        blocks = f" ({', '.join(passage.block_ids)})" if passage.block_ids else ""
        return f"p. {passage.page_id}{blocks}"
    return HEADING_SEPARATOR.join(passage.heading_path)


def references(cited: list[int], context: Context, options: WritingOptions) -> list[Reference]:
    """One entry per cited source, in order of first citation."""
    passages = {passage.n: passage for passage in context.passages}
    sources = {source.source_id: source for source in context.sources}
    order = list(dict.fromkeys(passages[n].source_id for n in cited))
    format_entry = style(options.reference_style)
    return [
        Reference(
            source_id=source_id,
            entry=format_entry(sources[source_id], k),
            passages=sorted(n for n in cited if passages[n].source_id == source_id),
        )
        for k, source_id in enumerate(order, start=1)
    ]


def reference_list(found: list[Reference], context: Context) -> str:
    passages = {passage.n: passage for passage in context.passages}
    lines = ["## References", ""]
    for reference in found:
        lines.append(f"- {reference.entry}")
        for n in reference.passages:
            locator = reference_locator(passages[n])
            lines.append(f"  - [{n}] {locator}" if locator else f"  - [{n}]")
    return "\n".join(lines)


def render(body: str, context: Context, options: WritingOptions) -> Report:
    passages = {passage.n: passage for passage in context.passages}
    sources = {source.source_id: source for source in context.sources}
    cited: list[int] = []
    warned: list[int] = []
    pieces: list[str] = []
    position = 0
    for start, end, numbers in citations(body):
        known = list(dict.fromkeys(n for n in numbers if n in passages))
        warned += [n for n in numbers if n not in passages and n not in warned]
        cited += [n for n in known if n not in cited]
        if known:
            pieces += [body[position:start], marker(known, options, passages, sources)]
        else:
            pieces.append(body[position:start].removesuffix(" "))
        position = end
    pieces.append(body[position:])
    warnings = [f"unknown citation [{n}]" for n in warned]
    markdown = "".join(pieces)
    found = references(cited, context, options)
    if cited:
        markdown = f"{markdown.rstrip()}\n\n{reference_list(found, context)}\n"
    else:
        warnings.append(NO_CITATIONS)
    return Report(body=body, markdown=markdown, cited=cited, references=found, warnings=warnings)


async def write(
    context: Context, options: WritingOptions, llm: LLM, *, on_delta: Callable[[str], None] = noop
) -> Report:
    description = tone_description(options.tone)
    style(options.reference_style)
    if not context.passages:
        raise ValueError("no passages to write from")
    pieces: list[str] = []
    reasons: list[str | None] = []
    limit = output_tokens(options.words)
    async for piece in llm.stream(messages(context, options, description), max_tokens=limit, on_finish=reasons.append):
        on_delta(piece)
        pieces.append(piece)
    report = render("".join(pieces), context, options)
    if reasons != ["length"]:
        return report
    truncated = f"report truncated at the output limit of {limit} tokens"
    return report.model_copy(update={"warnings": [*report.warnings, truncated]})

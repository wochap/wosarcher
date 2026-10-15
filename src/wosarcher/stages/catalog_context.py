"""Catalog context: pure code that turns `catalog.json` into numbered record passages for the writer.

One passage per assembled record in discovery order, added while it fits the
budget. The passage text is the name, the type, then one `<field>: <value>`
line per other non-null field; the slug, ref, and enum fields are carried as
the record ID, the heading path, and the type line instead. Record text only
ever reaches the writer inside its data block.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from wosarcher.models import CatalogRecord, Context, Node, Page, Passage, Source, Structure
from wosarcher.stages.select import estimate_tokens

SCORER = "catalog"


@dataclass(frozen=True)
class CatalogContext:
    context: Context
    total: int
    """Records in the catalog; the context holds the first `len(context.passages)`."""


def record_text(structure: Structure, record: dict[str, object]) -> str:
    name_field, enum_field = structure.name_field, structure.enum_field
    skipped = {name_field.name, enum_field.name}
    skipped |= {field.name for field in (structure.slug_field, structure.ref_field) if field is not None}
    lines = [str(record.get(name_field.name) or ""), str(record.get(enum_field.name) or "")]
    for field in structure.fields:
        value = record.get(field.name)
        if field.name not in skipped and value not in (None, ""):
            lines.append(f"{field.name}: {value}")
    return "\n".join(lines)


def coverage_task(brief: str, total: int, given: int) -> str:
    """The brief, with the coverage line when the passages hold fewer records than the catalog."""
    if given >= total:
        return brief
    return f"{brief}\n\nThe catalog has {total} records; the passages hold the first {given}."


def build(
    brief: str,
    structure: Structure,
    catalog: CatalogRecord,
    nodes: Sequence[Node],
    pages: Sequence[Page],
    *,
    budget_tokens: int,
    chars_per_token: float,
    margin: float,
) -> CatalogContext:
    """The record passages that fit `budget_tokens`, numbered from 1, and the writing task as the query."""
    extracted = [node for node in nodes if node.status == "extracted"]
    dropped = {item.node_id for item in catalog.dropped}
    kept = [node for node in extracted if node.id not in dropped]
    by_id = {node.id: node for node in nodes}
    page_of = {page.source.source_id: page for page in pages}
    passages: list[Passage] = []
    sources: dict[str, Source] = {}
    used = 0
    for node, record in zip(kept, catalog.records, strict=False):
        text = record_text(structure, record)
        parent = by_id.get(node.parent_id) if node.parent_id else None
        heading = [node.type, parent.name] if parent is not None else [node.type]
        first = next((page_of[source_id] for source_id in node.pages if source_id in page_of), None)
        source = (
            first.source
            if first is not None
            else Source(source_id=f"record:{node.id}", kind="file", uri=node.name, title=node.name)
        )
        cost = estimate_tokens(f"{source.title}\n{text}", chars_per_token=chars_per_token, margin=margin)
        if used + cost > budget_tokens:
            break
        used += cost
        sources.setdefault(source.source_id, source)
        passages.append(
            Passage(
                n=len(passages) + 1,
                chunk_id=f"record:{node.id}",
                source_id=source.source_id,
                query_id="q0",
                text=text,
                heading_path=heading,
                scorer=SCORER,
                record_id=node.id,
            )
        )
    total = len(catalog.records)
    context = Context(
        query=coverage_task(brief, total, len(passages)),
        passages=passages,
        sources=list(sources.values()),
        budget_tokens=budget_tokens,
        used_tokens=used,
    )
    return CatalogContext(context=context, total=total)

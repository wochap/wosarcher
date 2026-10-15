"""Assemble: pure code that turns the structure, the nodes, and the checked records into `catalog.json`.

Also home of the node slug and name normalisation the crawl uses for IDs and
dedupe, and of the stop notes.
"""

import re
import unicodedata
from collections.abc import Sequence

from wosarcher.models import (
    CatalogRecord,
    CatalogStopReason,
    DroppedRecord,
    ExtractedRecord,
    Node,
    Structure,
    WaveEntry,
)

NON_SLUG = re.compile(r"[^a-z0-9]+")
NON_WORD = re.compile(r"[^\w\s]")
SPACE = re.compile(r"\s+")


def ascii_fold(text: str) -> str:
    """NFD with combining marks removed."""
    return "".join(char for char in unicodedata.normalize("NFD", text) if not unicodedata.combining(char))


def slug(text: str) -> str:
    """Lower-case ASCII letters and digits, other runs as one hyphen, trimmed; `node` when nothing is left."""
    found = NON_SLUG.sub("-", ascii_fold(text).lower()).strip("-")
    return found or "node"


def unique_slug(text: str, taken: set[str]) -> str:
    """`slug(text)`, with `-2`, `-3`, … on collision; the result is added to `taken`."""
    base = slug(text)
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}-{n}"
    taken.add(candidate)
    return candidate


def normalised_name(text: str) -> str:
    """NFD, combining marks removed, case-folded, punctuation stripped, whitespace collapsed."""
    return SPACE.sub(" ", NON_WORD.sub(" ", ascii_fold(text).casefold())).strip()


STOP_NOTES: dict[CatalogStopReason, str] = {
    "frontier empty": "No unexpanded nodes left after wave {wave}.",
    "max nodes": "Max nodes {max_nodes} reached.",
    "page limit reached": "Page limit {max_pages} reached.",
    "extract failed": "Every extraction of wave {wave} failed.",
}


def stop_note(
    reason: CatalogStopReason, *, wave: int, structure: Structure, nodes: Sequence[Node], max_pages: int
) -> str:
    limits = structure.limits
    note = STOP_NOTES[reason].format(wave=wave, max_nodes=limits.max_nodes, max_pages=max_pages)
    if not any(node.depth >= limits.max_depth for node in nodes):
        note += f" Max depth {limits.max_depth} was not reached."
    return note


def assemble(
    structure: Structure,
    nodes: Sequence[Node],
    records: Sequence[ExtractedRecord],
    *,
    waves: Sequence[WaveEntry],
    reason: CatalogStopReason,
    note: str,
) -> CatalogRecord:
    """One record per extracted node in discovery order; records missing a required field go to `dropped`."""
    by_node = {record.node_id: record for record in records}
    slug_field, ref_field, enum_field = structure.slug_field, structure.ref_field, structure.enum_field
    generated = {field.name for field in (slug_field, ref_field, enum_field) if field is not None}
    assembled: list[dict[str, object]] = []
    dropped: list[DroppedRecord] = []
    fill = {field.name: 0 for field in structure.fields}
    by_type: dict[str, int] = {}
    by_depth: dict[str, int] = {}
    for node in nodes:
        found = by_node.get(node.id)
        if node.status != "extracted" or found is None:
            continue
        missing = next(
            (
                field.name
                for field in structure.fields
                if field.required and field.name not in generated and found.record.get(field.name) in (None, "")
            ),
            None,
        )
        if missing is not None:
            dropped.append(DroppedRecord(node_id=node.id, field=missing))
            continue
        entry: dict[str, object] = {}
        for field in structure.fields:
            if slug_field is not None and field.name == slug_field.name:
                value: object = node.id
            elif ref_field is not None and field.name == ref_field.name:
                value = node.parent_id
            elif field.name == enum_field.name:
                value = node.type
            else:
                value = found.record.get(field.name)
            entry[field.name] = value
            if value is not None:
                fill[field.name] += 1
        entry["sources"] = dict(found.sources)
        entry["flags"] = [*node.flags, *found.flags]
        assembled.append(entry)
        by_type[node.type] = by_type.get(node.type, 0) + 1
        by_depth[str(node.depth)] = by_depth.get(str(node.depth), 0) + 1
    return CatalogRecord(
        records=assembled,
        dropped=dropped,
        nodes=len(nodes),
        waves=list(waves),
        reason=reason,
        note=note,
        fill=fill,
        by_type=by_type,
        by_depth=by_depth,
    )

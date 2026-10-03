"""Search: run the Searcher for every query and merge hits by normalised URL."""

import asyncio
from collections.abc import Callable, Iterable, Sequence

from wosarcher.models import Hit, Query, SearchResult, Skipped, normalise_url
from wosarcher.ports import Searcher
from wosarcher.stages import noop


def merge_into(merged: dict[str, Hit], hits: Iterable[Hit]) -> list[Hit]:
    """Merge hits into `merged` (keyed by normalised URL); return the hits that were added or changed."""
    changed: list[Hit] = []
    for hit in hits:
        key = normalise_url(hit.url)
        old = merged.get(key)
        if old is None:
            new = hit.model_copy(update={"url": key, "query_ids": list(dict.fromkeys(hit.query_ids))})
        else:
            query_ids = list(dict.fromkeys([*old.query_ids, *hit.query_ids]))
            new = old.model_copy(update={"rank": min(old.rank, hit.rank), "query_ids": query_ids})
            if new == old:
                continue
        merged[key] = new
        changed.append(new)
    return changed


def merge_hits(lists: Iterable[Sequence[Hit]]) -> list[Hit]:
    """One hit per normalised URL: query IDs unioned in first-seen order, lowest rank, first title and snippet."""
    merged: dict[str, Hit] = {}
    for hits in lists:
        merge_into(merged, hits)
    return list(merged.values())


async def search(
    queries: Sequence[Query],
    searcher: Searcher,
    *,
    initial: Sequence[Hit] = (),
    on_item: Callable[[Hit], None] = noop,
) -> SearchResult:
    merged: dict[str, Hit] = {}
    merge_into(merged, initial)
    failures: list[Skipped] = []

    async def one(query: Query) -> None:
        try:
            hits = await searcher.search(query)
        except Exception as error:
            failures.append(Skipped(item=query.id, reason=str(error)))
            return
        for hit in merge_into(merged, hits):
            on_item(hit)

    await asyncio.gather(*(one(query) for query in queries))
    order = {query.id: n for n, query in enumerate(queries)}
    failures.sort(key=lambda failure: order[failure.item])
    return SearchResult(hits=list(merged.values()), failures=failures)

"""Search: run the Searcher for every query, drop hits by domain, and merge hits by normalised URL."""

import asyncio
from collections.abc import Callable, Iterable, Sequence
from urllib.parse import urlsplit

from wosarcher.models import Hit, Query, SearchResult, Skipped, host_matches, normalise_url
from wosarcher.ports import Searcher
from wosarcher.stages import noop

MAX_SEARCH_CHARS = 200
"""The longest query text sent to a search engine; also what counts as a short query."""


def cut(text: str, limit: int = MAX_SEARCH_CHARS) -> str:
    """`text` trimmed, cut at the last whitespace within `limit` (or at `limit` when there is none)."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit + 1]
    space = max(head.rfind(" "), head.rfind("\n"), head.rfind("\t"))
    return (head[:space] if space > 0 else text[:limit]).strip()


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


def allowed(url: str, allow: Sequence[str], block: Sequence[str]) -> bool:
    """Whether the URL's host passes the domain lists: not blocked, and allowed when the allow list is not empty."""
    host = urlsplit(url.strip()).netloc
    if host_matches(host, list(block)):
        return False
    return not allow or host_matches(host, list(allow))


async def search(
    queries: Sequence[Query],
    searcher: Searcher,
    *,
    initial: Sequence[Hit] = (),
    max_results: int = 10,
    allow: Sequence[str] = (),
    block: Sequence[str] = (),
    filter_pages: int = 3,
    on_item: Callable[[Hit], None] = noop,
) -> SearchResult:
    """Each query keeps at most `max_results` hits that pass the domain lists, ranked among the kept hits.

    While a list is set, a query short of hits reads further pages, up to `filter_pages`.
    """
    merged: dict[str, Hit] = {}
    merge_into(merged, initial)
    failures: list[Skipped] = []
    dropped: set[str] = set()
    filtering = bool(allow or block)

    async def one(query: Query) -> None:
        sent = query.model_copy(update={"text": cut(query.text)})
        kept: dict[str, Hit] = {}
        page = 1
        try:
            while True:
                found = await searcher.search(sent, page)
                for hit in found:
                    key = normalise_url(hit.url)
                    if not allowed(hit.url, allow, block):
                        dropped.add(key)
                    elif key not in kept and len(kept) < max_results:
                        kept[key] = hit.model_copy(update={"rank": len(kept) + 1})
                if not filtering or not found or len(kept) >= max_results or page >= filter_pages:
                    break
                page += 1
        except Exception as error:
            failures.append(Skipped(item=query.id, reason=str(error)))
        for hit in merge_into(merged, kept.values()):
            on_item(hit)

    await asyncio.gather(*(one(query) for query in queries))
    order = {query.id: n for n, query in enumerate(queries)}
    failures.sort(key=lambda failure: order[failure.item])
    return SearchResult(hits=list(merged.values()), failures=failures, filtered=len(dropped))

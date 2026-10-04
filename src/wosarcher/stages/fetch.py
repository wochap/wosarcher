"""Fetch: unique hit URLs in a fair queue, a few at a time, up to a page cap; failures are recorded, not raised.

The queue goes round-robin over query IDs in query order (`q0` first), each
query's hits by rank; a hit found by several queries is queued once, at its
earliest turn. A worker takes the next hit only while pages fetched plus
fetches in flight are below `max_pages`, so a failure frees its slot for the
next hit. Hits left in the queue are counted in `unfetched`, not recorded as
failures. The per-page character cap (`fetch.max_chars`) is the Fetcher's job;
this stage never cuts text.
"""

import asyncio
from collections import deque
from collections.abc import Callable, Sequence

from wosarcher.models import FetchResult, Hit, Page, Skipped
from wosarcher.ports import Fetcher
from wosarcher.stages import noop
from wosarcher.stages.search import merge_hits


def query_key(query_id: str) -> tuple[int, str]:
    """`q2` before `q10`."""
    return len(query_id), query_id


def fair_order(hits: Sequence[Hit]) -> list[Hit]:
    unique = merge_hits([hits])
    query_ids = sorted({query_id for hit in unique for query_id in hit.query_ids}, key=query_key)
    lanes = [
        deque(sorted((hit for hit in unique if query_id in hit.query_ids), key=lambda h: h.rank))
        for query_id in query_ids
    ]
    queued: dict[str, Hit] = {}
    while any(lanes):
        for lane in lanes:
            while lane and lane[0].url in queued:
                lane.popleft()
            if lane:
                hit = lane.popleft()
                queued[hit.url] = hit
    return list(queued.values())


async def fetch(
    hits: Sequence[Hit],
    fetcher: Fetcher,
    *,
    concurrency: int,
    max_pages: int,
    on_item: Callable[[Page | Skipped], None] = noop,
) -> FetchResult:
    queue = deque(enumerate(fair_order(hits)))
    outcomes: dict[int, Page | Skipped] = {}
    fetched = in_flight = 0

    async def one(hit: Hit) -> Page | Skipped:
        try:
            page = await fetcher.fetch(hit.url)
        except Exception as error:
            return Skipped(item=hit.url, reason=str(error))
        if not page.text.strip():
            return Skipped(item=hit.url, reason="empty content")
        return page.model_copy(update={"rank": hit.rank, "query_ids": list(hit.query_ids)})

    async def worker() -> None:
        nonlocal fetched, in_flight
        while queue and fetched + in_flight < max_pages:
            index, hit = queue.popleft()
            in_flight += 1
            try:
                outcome = await one(hit)
            finally:
                in_flight -= 1
            if isinstance(outcome, Page):
                fetched += 1
            outcomes[index] = outcome
            on_item(outcome)

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    ordered = [outcomes[index] for index in sorted(outcomes)]
    return FetchResult(
        pages=[item for item in ordered if isinstance(item, Page)],
        failures=[item for item in ordered if isinstance(item, Skipped)],
        unfetched=len(queue),
    )

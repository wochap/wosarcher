"""Fetch: unique hit URLs in a fair queue, a few at a time, up to a page cap; failures are recorded, not raised.

The queue goes round-robin over query IDs in query order (`q0` first), each
query's hits by rank; a hit found by several queries is queued once, at its
earliest turn. A worker takes the next hit only while counted pages plus
fetches in flight are below `max_pages`, so a failure frees its slot for the
next hit. A thin page (text shorter than `min_chars`) is kept but not
counted, up to `max_pages` thin pages per call; later thin pages count. Hits
left in the queue are counted in `unfetched`, not recorded as failures. The
per-page character cap (`fetch.max_chars`) is the Fetcher's job; this stage
never cuts text.
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


def is_thin(page: Page, min_chars: int) -> bool:
    return len(page.text) < min_chars


async def fetch(
    hits: Sequence[Hit],
    fetcher: Fetcher,
    *,
    concurrency: int,
    max_pages: int,
    min_chars: int = 0,
    on_item: Callable[[Page | Skipped], None] = noop,
) -> FetchResult:
    queue = deque(enumerate(fair_order(hits)))
    outcomes: dict[int, Page | Skipped] = {}
    counted = exempt = in_flight = 0

    async def one(hit: Hit) -> Page | Skipped:
        try:
            page = await fetcher.fetch(hit.url)
        except Exception as error:
            return Skipped(item=hit.url, reason=str(error))
        if not page.text.strip():
            return Skipped(item=hit.url, reason="empty content")
        return page.model_copy(update={"rank": hit.rank, "query_ids": list(hit.query_ids)})

    async def worker() -> None:
        nonlocal counted, exempt, in_flight
        while queue and counted + in_flight < max_pages:
            index, hit = queue.popleft()
            in_flight += 1
            try:
                outcome = await one(hit)
            finally:
                in_flight -= 1
            if isinstance(outcome, Page):
                if is_thin(outcome, min_chars) and exempt < max_pages:
                    exempt += 1
                else:
                    counted += 1
            outcomes[index] = outcome
            on_item(outcome)

    await asyncio.gather(*(worker() for _ in range(concurrency)))
    ordered = [outcomes[index] for index in sorted(outcomes)]
    return FetchResult(
        pages=[item for item in ordered if isinstance(item, Page)],
        failures=[item for item in ordered if isinstance(item, Skipped)],
        unfetched=len(queue),
        counted=counted,
    )

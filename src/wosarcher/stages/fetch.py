"""Fetch: each unique hit URL once, a few at a time; failures are recorded, not raised.

The page cap (`fetch.max_chars`) is the Fetcher's job; this stage never cuts text.
"""

import asyncio
from collections.abc import Callable, Sequence

from wosarcher.models import FetchResult, Hit, Page, Skipped
from wosarcher.ports import Fetcher
from wosarcher.stages import noop
from wosarcher.stages.search import merge_hits


async def fetch(
    hits: Sequence[Hit],
    fetcher: Fetcher,
    *,
    concurrency: int,
    on_item: Callable[[Page | Skipped], None] = noop,
) -> FetchResult:
    unique = merge_hits([hits])
    limit = asyncio.Semaphore(concurrency)

    async def one(hit: Hit) -> Page | Skipped:
        try:
            async with limit:
                page = await fetcher.fetch(hit.url)
        except Exception as error:
            outcome: Page | Skipped = Skipped(item=hit.url, reason=str(error))
        else:
            if page.text.strip():
                outcome = page.model_copy(update={"rank": hit.rank, "query_ids": list(hit.query_ids)})
            else:
                outcome = Skipped(item=hit.url, reason="empty content")
        on_item(outcome)
        return outcome

    outcomes = await asyncio.gather(*(one(hit) for hit in unique))
    return FetchResult(
        pages=[item for item in outcomes if isinstance(item, Page)],
        failures=[item for item in outcomes if isinstance(item, Skipped)],
    )

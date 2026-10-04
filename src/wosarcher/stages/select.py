"""Select: choose the cited passages the writer sees, within the token budget.

Only kept pairs count. Rules in order: per-source cap by within-query rank,
then round-robin across queries, best first, with soft file and web shares.
Passages are numbered in the order taken. Every kept passage not taken is
reported as a skip: `source_cap` when the per-source cap removed it, `budget`
when it was still left after the last round-robin pass.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from wosarcher.models import Chunk, Context, Page, Passage, Query, Score, Selection, SelectSkip

MIN_OUTPUT_TOKENS = 1024
LABEL_TOKENS = 16


def output_tokens(words: int) -> int:
    """Output allowance for the report; also the write stage's `max_tokens`."""
    return max(MIN_OUTPUT_TOKENS, 2 * words)


def budget(*, context_window: int, max_context_tokens: int, prompt_reserve_tokens: int, words: int) -> int:
    room = context_window - prompt_reserve_tokens - output_tokens(words)
    tokens = min(max_context_tokens, room)
    if tokens <= 0:
        raise ValueError(
            f"llm.context_window ({context_window}) is too small: it leaves {room} tokens for context after "
            f"{prompt_reserve_tokens} prompt and {output_tokens(words)} output tokens"
        )
    return tokens


def estimate_tokens(text: str, *, chars_per_token: float, margin: float) -> int:
    # Round first so float noise such as 220.00000000000003 does not add a token.
    return math.ceil(round(len(text) / chars_per_token * margin, 6))


@dataclass(frozen=True)
class Item:
    score: Score
    chunk: Chunk
    page: Page
    rank: int
    """Rank within its own query, 0 = best."""
    cost: int


def _round_robin(queues: Sequence[Sequence[Item]], budget_tokens: int) -> tuple[list[Item], list[Item]]:
    """One passage per query per round, in plan order; a passage that does not fit goes to `left`."""
    pending = [list(queue) for queue in queues]
    taken: list[Item] = []
    left: list[Item] = []
    used = 0
    while any(pending):
        for queue in pending:
            if not queue:
                continue
            item = queue.pop(0)
            if used + item.cost <= budget_tokens:
                taken.append(item)
                used += item.cost
            else:
                left.append(item)
    return taken, left


def _queues(items: Sequence[Item], queries: Sequence[Query]) -> list[list[Item]]:
    return [
        sorted((item for item in items if item.score.query_id == query.id), key=lambda item: item.rank)
        for query in queries
    ]


def _ranked(
    kept: Sequence[Score],
    chunks: dict[str, Chunk],
    pages: dict[str, Page],
    page_index: dict[str, int],
    cost: dict[str, int],
) -> list[Item]:
    """Each kept pair with its rank within its own query (best value first, then page order)."""
    items: list[Item] = []
    for query_id in dict.fromkeys(score.query_id for score in kept):
        own = [score for score in kept if score.query_id == query_id]

        def key(score: Score) -> tuple[float, int, int]:
            chunk = chunks[score.chunk_id]
            return -score.value, page_index[chunk.source_id], chunk.position

        for rank, score in enumerate(sorted(own, key=key)):
            chunk = chunks[score.chunk_id]
            items.append(Item(score, chunk, pages[chunk.source_id], rank, cost[chunk.chunk_id]))
    return items


def _source_cap(
    items: Sequence[Item], max_per_source: int, plan_index: dict[str, int]
) -> tuple[list[Item], list[Item]]:
    """The items within the cap of their source, and the items it removes."""
    by_source: dict[str, list[Item]] = {}
    for item in items:
        by_source.setdefault(item.chunk.source_id, []).append(item)
    capped: list[Item] = []
    removed: list[Item] = []
    for group in by_source.values():
        group.sort(key=lambda item: (item.rank, -(item.score.display or 0.0), plan_index[item.score.query_id]))
        capped.extend(group[:max_per_source])
        removed.extend(group[max_per_source:])
    return capped, removed


def _skip(item: Item, tokens_left: int | None = None) -> SelectSkip:
    """`source_cap` without `tokens_left`, `budget` with it."""
    if tokens_left is None:
        return SelectSkip(chunk_id=item.chunk.chunk_id, query_id=item.score.query_id, reason="source_cap")
    return SelectSkip(
        chunk_id=item.chunk.chunk_id,
        query_id=item.score.query_id,
        reason="budget",
        tokens_needed=item.cost,
        tokens_left=tokens_left,
    )


def select(
    query: str,
    scores: Sequence[Score],
    pages: Sequence[Page],
    chunks: Sequence[Chunk],
    queries: Sequence[Query],
    *,
    budget_tokens: int,
    max_per_source: int,
    file_share: float,
    chars_per_token: float,
    margin: float,
) -> Selection:
    chunk_of = {chunk.chunk_id: chunk for chunk in chunks}
    page_of = {page.source.source_id: page for page in pages}
    page_index = {page.source.source_id: i for i, page in enumerate(pages)}
    plan_index = {query.id: i for i, query in enumerate(queries)}
    first: dict[str, Score] = {}
    for score in scores:
        if score.kept:
            first.setdefault(score.chunk_id, score)
    kept = list(first.values())
    cost = {
        score.chunk_id: estimate_tokens(chunk_of[score.chunk_id].text, chars_per_token=chars_per_token, margin=margin)
        + LABEL_TOKENS
        for score in kept
    }
    items, removed = _source_cap(_ranked(kept, chunk_of, page_of, page_index, cost), max_per_source, plan_index)

    files = [item for item in items if item.page.source.kind == "file"]
    web = [item for item in items if item.page.source.kind == "web"]
    file_budget = budget_tokens if not web else 0 if not files else math.floor(file_share * budget_tokens)
    taken_files, left_files = _round_robin(_queues(files, queries), file_budget)
    taken_web, left_web = _round_robin(_queues(web, queries), budget_tokens - file_budget)
    taken = [*taken_files, *taken_web]
    used = sum(item.cost for item in taken)
    more, left = _round_robin(_queues([*left_files, *left_web], queries), budget_tokens - used)
    taken.extend(more)
    used_tokens = sum(item.cost for item in taken)
    skipped = [
        *(_skip(item) for item in removed),
        *(_skip(item, budget_tokens - used_tokens) for item in left),
    ]

    passages = [
        Passage(
            n=n,
            chunk_id=item.chunk.chunk_id,
            source_id=item.chunk.source_id,
            query_id=item.score.query_id,
            text=item.chunk.text,
            heading_path=item.chunk.heading_path,
            page_id=item.chunk.page_id,
            block_ids=item.chunk.block_ids,
            scorer=item.score.scorer,
            display=item.score.display,
        )
        for n, item in enumerate(taken, start=1)
    ]
    sources = list({item.chunk.source_id: item.page.source for item in taken}.values())
    context = Context(
        query=query, passages=passages, sources=sources, budget_tokens=budget_tokens, used_tokens=used_tokens
    )
    return Selection(context=context, skipped=skipped)

"""Score: score the prefiltered pairs with one scorer per run, then threshold, dedupe, and cap.

The configured scorer runs first; when any call fails, every score from it is
discarded and the stage starts again with the next entry of `score.fallback`,
so one run never mixes score scales. `passthrough` never fails. Small-input
candidates always get passthrough scores.
"""

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from functools import partial

from wosarcher.config import ScoreConfig
from wosarcher.lexical import bm25_scores, rank
from wosarcher.models import Candidate, Chunk, Page, Query, QueryScores, Score, ScoreResult, Skipped
from wosarcher.ports import Scorer

JEV_MAX = 3.0
BM25_MAX_RESULTS = 25


def noop(_: QueryScores) -> None:
    pass


@dataclass(frozen=True)
class Group:
    """One query's pairs: chunks in page order, and whether they are small-input passthrough."""

    query: Query
    chunks: list[Chunk]
    passthrough: bool


# Thresholds and display


def _keep_calibrated(values: Sequence[float], min_score: float) -> set[int]:
    return {i for i, value in enumerate(values) if value >= min_score}


def _keep_relative(values: Sequence[float], relative_threshold: float) -> set[int]:
    if not values:
        return set()
    best = max(values)
    if best <= 0:
        return {values.index(best)}
    return {i for i, value in enumerate(values) if value >= relative_threshold * best}


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _display(name: str, value: float, best: float) -> float | None:
    if name == "passthrough":
        return None
    if name == "jev":
        return _clamp(value / JEV_MAX)
    if name == "bm25":
        return _clamp(value / best) if best > 0 else 0.0
    return _clamp(value)


def _threshold_display(name: str, cfg: ScoreConfig, best: float | None) -> float | None:
    if name == "passthrough":
        return None
    if name == "jev":
        return _clamp(cfg.min_score / JEV_MAX)
    if name == "bm25":
        return cfg.relative_threshold
    shown = None if best is None else _display(name, best, best)
    return None if shown is None else cfg.relative_threshold * shown


def _kept(name: str, calibrated: bool, group: Group, values: Sequence[float], cfg: ScoreConfig) -> set[int]:
    if name == "passthrough":
        return set(range(len(values)))
    if name == "bm25":
        texts = [chunk.text for chunk in group.chunks]
        kept = rank(group.query.text, texts, relative_threshold=cfg.relative_threshold, max_results=BM25_MAX_RESULTS)
        return set(kept)
    if calibrated:
        return _keep_calibrated(values, cfg.min_score)
    return _keep_relative(values, cfg.relative_threshold)


# Running one chain entry


def passthrough_order(group: Group, pages: dict[str, Page], page_index: dict[str, int]) -> list[Chunk]:
    """Search rank, then page order, then chunk position."""

    def key(chunk: Chunk) -> tuple[int, int, int]:
        return pages[chunk.source_id].rank, page_index[chunk.source_id], chunk.position

    return sorted(group.chunks, key=key)


async def raw_values(name: str, group: Group, scorer: Scorer | None) -> list[float]:
    """One value per chunk of `group`, in its order; raises when the scorer fails."""
    if not group.chunks:
        return []
    if name == "passthrough":
        return [float(len(group.chunks) - i) for i in range(len(group.chunks))]
    if name == "bm25":
        return bm25_scores(group.query.text, [chunk.text for chunk in group.chunks])
    if scorer is None or scorer.name != name:
        raise RuntimeError(f"scorer {name} not configured")
    found = {score.chunk_id: score.value for score in await scorer.score(group.query, group.chunks)}
    missing = [chunk.chunk_id for chunk in group.chunks if chunk.chunk_id not in found]
    if missing:
        raise RuntimeError(f"scorer {name} returned no score for {len(missing)} chunks")
    return [found[chunk.chunk_id] for chunk in group.chunks]


async def gather[T](calls: Sequence[Callable[[], Coroutine[object, object, T]]]) -> list[T]:
    """Run concurrently; the first failure cancels the rest and is raised as is."""
    tasks: list[asyncio.Task[T]] = []
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(call()) for call in calls]
    except ExceptionGroup as errors:
        raise errors.exceptions[0] from None
    return [task.result() for task in tasks]


def scored_pairs(name: str, calibrated: bool, group: Group, values: Sequence[float], cfg: ScoreConfig) -> list[Score]:
    """Every pair of the group with value, display, and threshold result."""
    kept = _kept(name, calibrated, group, values, cfg)
    best = max(values, default=0.0)
    return [
        Score(
            query_id=group.query.id,
            chunk_id=chunk.chunk_id,
            value=values[i],
            scorer=name,
            display=_display(name, values[i], best),
            kept=i in kept,
        )
        for i, chunk in enumerate(group.chunks)
    ]


# Best pair per chunk and per-query cap


def best_pair_only(scores: list[Score], plan_index: dict[str, int]) -> list[Score]:
    """Keep each chunk's kept pair with the highest display; ties go to the earlier query."""
    best: dict[str, Score] = {}
    for score in scores:
        if not score.kept:
            continue
        current = best.get(score.chunk_id)
        order = (-(score.display or 0.0), plan_index[score.query_id])
        if current is None or order < (-(current.display or 0.0), plan_index[current.query_id]):
            best[score.chunk_id] = score
    return [
        score.model_copy(update={"kept": False}) if score.kept and best[score.chunk_id] is not score else score
        for score in scores
    ]


def capped(scores: list[Score], top_k: int) -> list[Score]:
    """One query's scores in page order; keep at most `top_k` kept pairs by value."""
    kept = sorted((i for i, score in enumerate(scores) if score.kept), key=lambda i: (-scores[i].value, i))
    allowed = set(kept[:top_k])
    return [
        score.model_copy(update={"kept": False}) if score.kept and i not in allowed else score
        for i, score in enumerate(scores)
    ]


def report(group: Group, name: str, scores: list[Score], cfg: ScoreConfig) -> QueryScores:
    order = sorted(range(len(scores)), key=lambda i: (-scores[i].value, i))
    passages = [scores[i] for i in order if scores[i].kept]
    best = max((score.value for score in scores), default=None)
    return QueryScores(
        query_id=group.query.id,
        scorer=name,
        scored=len(scores),
        kept=len(passages),
        threshold_display=_threshold_display(name, cfg, best),
        passages=passages,
    )


async def score(
    candidates: Sequence[Candidate],
    queries: Sequence[Query],
    pages: Sequence[Page],
    chunks: Sequence[Chunk],
    scorer: Scorer | None,
    *,
    cfg: ScoreConfig,
    on_item: Callable[[QueryScores], None] = noop,
) -> ScoreResult:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    page_of = {page.source.source_id: page for page in pages}
    page_index = {page.source.source_id: i for i, page in enumerate(pages)}
    plan_index = {query.id: i for i, query in enumerate(queries)}

    def page_order(chunk: Chunk) -> tuple[int, int]:
        return page_index[chunk.source_id], chunk.position

    groups: list[Group] = []
    for query in queries:
        own = [candidate for candidate in candidates if candidate.query_id == query.id]
        group = Group(query, sorted((by_id[c.chunk_id] for c in own), key=page_order), any(c.passthrough for c in own))
        if group.passthrough:
            group = Group(query, passthrough_order(group, page_of, page_index), True)
        groups.append(group)
    ranked = [group for group in groups if not group.passthrough]

    chain = [cfg.provider, *[entry for entry in cfg.fallback if entry != cfg.provider]]
    if "passthrough" not in chain:
        chain.append("passthrough")
    failed: list[Skipped] = []
    name = chain[0]
    values: list[list[float]] = []
    for name in chain:
        if name == "passthrough":
            ranked = [Group(g.query, passthrough_order(g, page_of, page_index), False) for g in ranked]
        try:
            values = await gather([partial(raw_values, name, group, scorer) for group in ranked])
        except Exception as error:
            failed.append(Skipped(item=name, reason=str(error) or type(error).__name__))
            continue
        break

    calibrated = scorer is not None and scorer.name == name and scorer.calibrated
    used = {group.query.id: (name, group, vals) for group, vals in zip(ranked, values, strict=True)}
    for group in groups:
        if group.passthrough:
            used[group.query.id] = ("passthrough", group, await raw_values("passthrough", group, None))

    per_query = {
        query_id: scored_pairs(entry, calibrated, group, vals, cfg) for query_id, (entry, group, vals) in used.items()
    }
    flat = best_pair_only([s for group in groups for s in per_query[group.query.id]], plan_index)
    reports: list[QueryScores] = []
    scores: list[Score] = []
    for group in groups:
        entry = used[group.query.id][0]
        own = [s for s in flat if s.query_id == group.query.id]
        if entry != "passthrough":
            own = capped(own, cfg.top_k)
        scores.extend(own)
        reports.append(report(group, entry, own, cfg))
    for item in reports:
        on_item(item)
    return ScoreResult(scores=scores, scorer=name, failed=failed, queries=reports)

"""Score: score the prefiltered pairs with one scorer per run, then threshold, cap, and dedupe.

The configured scorer runs first; when any call fails, every score from it is
discarded and the stage starts again with the next entry of `score.fallback`,
so one run never mixes score scales. The chain is exactly the configured
scorer plus `score.fallback`; when every entry fails, the stage raises
`ScoreChainError`. `passthrough` never fails. Small-input candidates always
get passthrough scores.

Each pair goes through three rules in order: the scorer's threshold, the
per-query cap (`score.top_k`; small-input passthrough keeps its first
`top_k` in passthrough order, the `passthrough` fallback scorer is not
capped), and the best pair per
chunk across queries. A pair one rule drops records it in `dropped` and takes
no part in the later rules.
"""

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from functools import partial
from math import exp
from typing import Literal

from wosarcher.config import ScoreConfig
from wosarcher.lexical import bm25_scores, rank
from wosarcher.models import Candidate, Chunk, Page, Query, QueryScores, Score, ScoreResult, Skipped
from wosarcher.ports import Scorer

JEV_MAX = 3.0
BM25_MAX_RESULTS = 25

type Scale = Literal["probability", "logit"]


class ScoreChainError(RuntimeError):
    """Every scorer of the chain failed."""


def noop(_: QueryScores) -> None:
    pass


@dataclass(frozen=True)
class Group:
    """One query's pairs: chunks in page order, and whether they are small-input passthrough."""

    query: Query
    chunks: list[Chunk]
    passthrough: bool


# Thresholds and display


def stage_scale(cfg: ScoreConfig, values: Sequence[Sequence[float]]) -> Scale:
    """The configured rerank scale; for `auto`, `logit` when any value of the stage is outside [0, 1]."""
    if cfg.rerank_scale != "auto":
        return cfg.rerank_scale
    return "logit" if any(not 0 <= value <= 1 for group in values for value in group) else "probability"


def mapped(name: str, scale: Scale, value: float) -> float:
    """Rerank logits through the logistic sigmoid (stable for large negative values); anything else as is."""
    if name != "rerank" or scale != "logit":
        return value
    if value >= 0:
        return 1 / (1 + exp(-value))
    small = exp(value)
    return small / (1 + small)


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


def threshold_display(name: str, cfg: ScoreConfig, best: float | None) -> float | None:
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


def scored_pairs(
    name: str, calibrated: bool, group: Group, values: Sequence[float], cfg: ScoreConfig, scale: Scale
) -> list[Score]:
    """Every pair of the group with raw value, display, and threshold result (on the mapped values)."""
    shown = [mapped(name, scale, value) for value in values]
    kept = _kept(name, calibrated, group, shown, cfg)
    best = max(shown, default=0.0)
    return [
        Score(
            query_id=group.query.id,
            chunk_id=chunk.chunk_id,
            value=values[i],
            scorer=name,
            display=_display(name, shown[i], best),
            kept=i in kept,
            dropped=None if i in kept else "threshold",
        )
        for i, chunk in enumerate(group.chunks)
    ]


# Per-query cap and best pair per chunk


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
        score.model_copy(update={"kept": False, "dropped": "other_query"})
        if score.kept and best[score.chunk_id] is not score
        else score
        for score in scores
    ]


def keep_once(scores: list[Score], queries: Sequence[Query]) -> list[Score]:
    """Across rounds, keep each chunk for one query only: the earliest round's kept pair, then plan order."""
    plan_index = {query.id: i for i, query in enumerate(queries)}
    first: dict[str, Score] = {}
    for score in scores:
        if not score.kept:
            continue
        current = first.get(score.chunk_id)
        order = (score.round, plan_index.get(score.query_id, len(plan_index)))
        if current is None or order < (current.round, plan_index.get(current.query_id, len(plan_index))):
            first[score.chunk_id] = score
    return [
        score.model_copy(update={"kept": False, "dropped": "other_query"})
        if score.kept and first[score.chunk_id] is not score
        else score
        for score in scores
    ]


def capped(scores: list[Score], top_k: int) -> list[Score]:
    """One query's scores in page order; keep at most `top_k` kept pairs by value."""
    kept = sorted((i for i, score in enumerate(scores) if score.kept), key=lambda i: (-scores[i].value, i))
    allowed = set(kept[:top_k])
    return [
        score.model_copy(update={"kept": False, "dropped": "query_cap"}) if score.kept and i not in allowed else score
        for i, score in enumerate(scores)
    ]


def report(group: Group, name: str, scores: list[Score], cfg: ScoreConfig, scale: Scale) -> QueryScores:
    order = sorted(range(len(scores)), key=lambda i: (-scores[i].value, i))
    passages = [scores[i] for i in order if scores[i].kept]
    best = max((mapped(name, scale, score.value) for score in scores), default=None)
    return QueryScores(
        query_id=group.query.id,
        scorer=name,
        scored=len(scores),
        kept=len(passages),
        threshold_display=threshold_display(name, cfg, best),
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
    failed: list[Skipped] = []
    name = chain[0]
    values: list[list[float]] | None = None
    for name in chain:
        if name == "passthrough":
            ranked = [Group(g.query, passthrough_order(g, page_of, page_index), False) for g in ranked]
        try:
            values = await gather([partial(raw_values, name, group, scorer) for group in ranked])
        except Exception as error:
            failed.append(Skipped(item=name, reason=str(error) or type(error).__name__))
            continue
        break
    if values is None:
        reasons = "; ".join(f"{skipped.item}: {skipped.reason}" for skipped in failed)
        raise ScoreChainError(f"every scorer failed: {reasons}")

    calibrated = scorer is not None and scorer.name == name and scorer.calibrated
    scale: Scale = stage_scale(cfg, values) if name == "rerank" else "probability"
    used = {group.query.id: (name, group, vals) for group, vals in zip(ranked, values, strict=True)}
    for group in groups:
        if group.passthrough:
            used[group.query.id] = ("passthrough", group, await raw_values("passthrough", group, None))

    per_query: dict[str, list[Score]] = {}
    for query_id, (entry, group, vals) in used.items():
        own = scored_pairs(entry, calibrated, group, vals, cfg, scale)
        uncapped = entry == "passthrough" and not group.passthrough
        per_query[query_id] = own if uncapped else capped(own, cfg.top_k)
    scores = best_pair_only([s for group in groups for s in per_query[group.query.id]], plan_index)
    reports = [
        report(group, used[group.query.id][0], [s for s in scores if s.query_id == group.query.id], cfg, scale)
        for group in groups
    ]
    for item in reports:
        on_item(item)
    return ScoreResult(scores=scores, scorer=name, failed=failed, queries=reports)

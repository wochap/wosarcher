"""`GET /api/runs/{id}/sources/{source_id}`: one source's chunks with the fate of each, from the run's artifacts.

Files come before web pages, as the runner orders them. `source_view` is pure: it reads what the
stages decided and runs no stage.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from wosarcher.config import ScoreConfig, SelectConfig
from wosarcher.models import (
    Candidate,
    Chunk,
    ChunkFate,
    ChunkQueryFate,
    ChunkQueryState,
    Context,
    Page,
    Plan,
    RunRecord,
    Score,
    SelectSkip,
    SourceChunk,
    SourceView,
)
from wosarcher.server.errors import RouteError, not_found
from wosarcher.server.routes import record_of
from wosarcher.server.state import ServerState, get_state
from wosarcher.stages.score import threshold_display

router = APIRouter(prefix="/api/runs")
State = Annotated[ServerState, Depends(get_state)]

DROPPED: dict[str, ChunkQueryState] = {
    "threshold": "below_threshold",
    "query_cap": "query_cap",
    "other_query": "other_query",
}


def is_ranked(score: Score) -> bool:
    """At or above the threshold: kept, or dropped only by a later rule."""
    return score.kept or score.dropped in ("query_cap", "other_query")


def pair_state(score: Score) -> ChunkQueryState:
    return "kept" if score.kept else DROPPED[score.dropped or "threshold"]


def source_view(
    record: RunRecord,
    plan: Plan | None,
    pages: list[Page],
    chunks: list[Chunk],
    candidates: list[Candidate] | None,
    scores: list[Score],
    skips: list[SelectSkip],
    context: Context | None,
    source_id: str,
) -> SourceView | None:
    """None when `source_id` is not one of `pages`. `candidates` is None before the prefilter stage ran."""
    page = next((page for page in pages if page.source.source_id == source_id), None)
    if page is None:
        return None
    score_cfg = ScoreConfig.model_validate(record.settings.get("score") or {"provider": "bm25"})
    select_cfg = SelectConfig.model_validate(record.settings.get("select") or {})
    queries = plan.queries if plan else []
    page_index = {p.source.source_id: i for i, p in enumerate(pages)}
    order = {c.chunk_id: (page_index.get(c.source_id, len(pages)), c.position) for c in chunks}

    by_pair = {(s.chunk_id, s.query_id): s for s in scores}
    paired = {(c.chunk_id, c.query_id) for c in candidates or []}
    cited = {p.chunk_id: p for p in context.passages} if context else {}
    skipped = {s.chunk_id: s for s in skips}

    ranks: dict[tuple[str, str], int] = {}
    ranked: dict[str, int] = {}
    kept: dict[str, int] = {}
    thresholds: dict[str, float | None] = {}
    for query in queries:
        own = [s for s in scores if s.query_id == query.id]
        if not own:
            continue
        above = sorted((s for s in own if is_ranked(s)), key=lambda s: (-s.value, order.get(s.chunk_id, (0, 0))))
        ranks.update({(s.chunk_id, query.id): i + 1 for i, s in enumerate(above)})
        ranked[query.id] = len(above)
        kept[query.id] = sum(s.kept for s in own)
        best = max((s.display for s in own if s.display is not None), default=None)
        thresholds[query.id] = threshold_display(own[0].scorer, score_cfg, best)

    def state(chunk: Chunk, query_id: str) -> ChunkQueryState:
        if page.source.kind == "web" and query_id not in page.query_ids:
            return "not_in_results"
        if candidates is None:
            return "pending"
        if (chunk.chunk_id, query_id) not in paired:
            return "prefiltered"
        found = by_pair.get((chunk.chunk_id, query_id))
        return "pending" if found is None else pair_state(found)

    def fate_at(score: Score, kind: str, **extra: int | None) -> ChunkFate:
        return ChunkFate.model_validate(
            {
                "kind": kind,
                "query_id": score.query_id,
                "display": score.display,
                "rank": ranks.get((score.chunk_id, score.query_id)),
                "ranked": ranked.get(score.query_id),
                "kept_in_query": kept.get(score.query_id),
                **extra,
            }
        )

    def fate(chunk: Chunk, rows: list[ChunkQueryFate]) -> ChunkFate:
        own = [s for q in queries if (s := by_pair.get((chunk.chunk_id, q.id))) is not None]
        primary = next((s for s in own if s.kept), None)
        if primary is not None:
            if (passage := cited.get(chunk.chunk_id)) is not None:
                return fate_at(primary, "cited", n=passage.n)
            if (skip := skipped.get(chunk.chunk_id)) is not None:
                return fate_at(primary, skip.reason, tokens_needed=skip.tokens_needed, tokens_left=skip.tokens_left)
            return fate_at(primary, "kept")
        capped = [s for s in own if s.dropped == "query_cap"]
        if capped or own:
            best = max(capped or own, key=lambda s: s.display if s.display is not None else s.value)
            return fate_at(best, "query_cap" if capped else "below_threshold")
        return ChunkFate(kind="pending" if any(row.state == "pending" for row in rows) else "prefiltered")

    own_chunks = sorted((c for c in chunks if c.source_id == source_id), key=lambda c: c.position)
    rows: list[SourceChunk] = []
    previous = -1
    for chunk in own_chunks:
        queries_of = [
            ChunkQueryFate(query_id=q.id, state=state(chunk, q.id), display=found.display if found else None)
            for q in queries
            for found in [by_pair.get((chunk.chunk_id, q.id))]
        ]
        rows.append(
            SourceChunk(
                chunk_id=chunk.chunk_id,
                position=chunk.position,
                heading_path=chunk.heading_path,
                text=chunk.text,
                removed_before=max(0, chunk.position - previous - 1),
                queries=queries_of,
                fate=fate(chunk, queries_of),
                floor=any(s.kept and s.floor for q in queries if (s := by_pair.get((chunk.chunk_id, q.id)))),
            )
        )
        previous = chunk.position

    shown = set(thresholds.values())
    main = queries[0].id if queries else ""
    threshold = next(iter(shown)) if len(shown) == 1 else thresholds.get(main)
    return SourceView(
        source=page.source,
        truncated=page.truncated,
        queries=queries,
        threshold=threshold,
        query_cap=score_cfg.top_k,
        source_cap=select_cfg.max_chunks_per_source,
        chunks=rows,
    )


@router.get("/{run_id}/sources/{source_id}")
async def show_source(state: State, run_id: str, source_id: str) -> SourceView:
    record = record_of(state, run_id)
    if record is None:
        raise not_found(run_id)
    store, folder = state.store, state.runs_dir / run_id
    view = source_view(
        record,
        store.read_artifact(run_id, "plan.json", Plan) if (folder / "plan.json").is_file() else None,
        [*store.read_items(run_id, "files.jsonl", Page), *store.read_items(run_id, "pages.jsonl", Page)],
        store.read_items(run_id, "chunks.jsonl", Chunk),
        store.read_items(run_id, "candidates.jsonl", Candidate) if (folder / "candidates.jsonl").is_file() else None,
        store.read_items(run_id, "scores.jsonl", Score),
        store.read_items(run_id, "select.jsonl", SelectSkip),
        store.read_artifact(run_id, "context.json", Context) if (folder / "context.json").is_file() else None,
        source_id,
    )
    if view is None:
        raise RouteError(404, "source_not_found", f"no source {source_id} in run {run_id}")
    return view

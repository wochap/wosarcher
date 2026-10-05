"""One async function per stage: read inputs from earlier artifacts, call the stage, write its artifact.

Each step returns an `Outcome`; the runner turns it into `stage.done`.
"""

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from wosarcher.attachments import collect
from wosarcher.config import DEFAULT_CONCURRENCY, Settings
from wosarcher.models import (
    Attachment,
    Candidate,
    Chunk,
    Context,
    GapReadyData,
    GapResult,
    Hit,
    HitFoundData,
    KeptPassage,
    Page,
    PageFailedData,
    PageFetchedData,
    PassagesScoredData,
    Plan,
    PlanReadyData,
    Query,
    QueryScores,
    ReportTextData,
    RunRecord,
    Score,
    SearchResult,
    Skipped,
    Stage,
    StageFailedData,
    normalise_url,
)
from wosarcher.ports import Adapters, Searcher
from wosarcher.runner.caches import CachedFetcher, EmbeddingMapping
from wosarcher.runner.devices import stage_provider
from wosarcher.runner.events import EventLog
from wosarcher.stages import chunk as chunking
from wosarcher.stages import fetch as fetching
from wosarcher.stages import gap as gapping
from wosarcher.stages import load as loading
from wosarcher.stages import plan as planning
from wosarcher.stages import prefilter as prefiltering
from wosarcher.stages import score as scoring
from wosarcher.stages import search as searching
from wosarcher.stages import select as selecting
from wosarcher.stages import write as writing
from wosarcher.store import RunStore
from wosarcher.store.caches import EmbeddingCache

log = logging.getLogger(__name__)

REASON_MAX_CHARS = 200


@dataclass
class RoundState:
    """The research loop's bookkeeping; a single-round run stays in round 1."""

    number: int = 1
    fetched: int = 0
    """Pages fetched across all rounds."""
    seen: set[str] = field(default_factory=set[str])
    """URLs fetched or queued in any round."""
    scorer: str | None = None
    """The scorer that last ran; later rounds start with it."""
    new_pages: int = 0
    previous_new_pages: int = 0
    """The previous round's `new_pages`; `no new sources` needs two empty rounds in a row."""
    known_pages: int = 0
    kept: int = 0
    gap: GapResult | None = None
    gap_error: str | None = None

    def next(self) -> None:
        self.number += 1
        self.previous_new_pages = self.new_pages
        self.new_pages = self.known_pages = self.kept = 0
        self.gap = self.gap_error = None


@dataclass
class StepContext:
    store: RunStore
    record: RunRecord
    settings: Settings
    adapters: Adapters
    log: EventLog
    fetcher: CachedFetcher
    round: RoundState = field(default_factory=RoundState)

    @property
    def run_id(self) -> str:
        return self.record.run_id

    @property
    def first(self) -> bool:
        return self.round.number == 1

    def save(self, name: str, items: Sequence[BaseModel]) -> None:
        """Round 1 writes the artifact; later rounds append to it."""
        if self.first:
            self.store.write_artifact(self.run_id, name, items)
        else:
            self.store.append_jsonl(self.run_id, name, items)

    def planned_rounds(self) -> int:
        """`research.rounds`, or 1 for files-only runs and plans without a sub-query."""
        if self.record.request.sources == "files" or len(self.plan().queries) < 2:
            return 1
        return self.settings.research.rounds

    def round_queries(self) -> list[Query]:
        return [query for query in self.plan().queries if query.round == self.round.number]

    def round_pages(self) -> list[Page]:
        """Round 1: every page; later rounds: the files and the pages fetched this round."""
        pages = self.pages()
        return (
            pages
            if self.first
            else [page for page in pages if page.source.kind == "file" or page.round == self.round.number]
        )

    def round_chunks(self, pages: Sequence[Page]) -> list[Chunk]:
        sources = {page.source.source_id for page in pages}
        return [piece for piece in self.items("chunks.jsonl", Chunk) if piece.source_id in sources]

    def items[T: Page | Hit | Chunk | Candidate | Score](self, name: str, model_type: type[T]) -> list[T]:
        return self.store.read_items(self.run_id, name, model_type)

    def pages(self) -> list[Page]:
        return [*self.items("files.jsonl", Page), *self.items("pages.jsonl", Page)]

    def plan(self) -> Plan:
        return self.store.read_artifact(self.run_id, "plan.json", Plan)


@dataclass
class Outcome:
    count: int
    """Items the stage produced; for `write`, characters of report text."""
    provider: str | None = None
    warnings: list[str] = field(default_factory=list[str])
    passthrough: list[str] = field(default_factory=list[str])
    unfetched: int = 0
    filtered: int = 0


async def run_search(
    ctx: "StepContext", queries: Sequence[Query], searcher: Searcher, stage: Stage, initial: Sequence[Hit] = ()
) -> SearchResult:
    """The search stage with the run's result cap and domain lists."""
    cfg = ctx.settings.search
    return await searching.search(
        queries,
        searcher,
        initial=initial,
        max_results=cfg.max_results,
        allow=cfg.allow_domains,
        block=cfg.block_domains,
        filter_pages=cfg.filter_pages,
        on_item=hit_found(ctx, stage),
    )


def short_reason(text: str) -> str:
    """The first line of an error, at most 200 characters, ending with `…` when cut."""
    lines = text.strip().splitlines()
    first = lines[0] if lines else ""
    if len(first) <= REASON_MAX_CHARS and len(lines) <= 1:
        return first
    return first[: REASON_MAX_CHARS - 1] + "…"


def failures(items: list[Skipped]) -> list[str]:
    return [f"{item.item}: {item.reason}" for item in items]


def round_cap(left: int, later: int, queries_per_round: int, max_results: int) -> int:
    """Pages this round may fetch: `left` minus a reserve for the `later` rounds, at least an even share."""
    reserve = queries_per_round * max_results * later
    even = math.ceil(left / (later + 1))
    return min(max(left - reserve, even), left)


def hit_found(ctx: StepContext, stage: Stage) -> Callable[[Hit], None]:
    def on_item(hit: Hit) -> None:
        ctx.log.emit("hit.found", stage, HitFoundData(url=hit.url, title=hit.title, query_ids=hit.query_ids))

    return on_item


async def load(ctx: StepContext) -> Outcome:
    root = ctx.store.run_dir(ctx.run_id) / "attachments"
    found: list[Attachment] = []
    skipped: list[Skipped] = []
    if root.is_dir() and any(path.is_file() for path in root.rglob("*")):
        found, skipped = collect([str(root)], max_bytes=ctx.settings.attach.max_bytes)

    def relative(name: str) -> str:
        return Path(name).resolve().relative_to(root.resolve()).as_posix()

    named = [item.model_copy(update={"name": relative(item.name)}) for item in found]
    skipped = [item.model_copy(update={"item": relative(item.item)}) for item in skipped]
    result = loading.load(named)
    ctx.store.write_artifact(ctx.run_id, "files.jsonl", result.pages)
    return Outcome(len(result.pages), warnings=failures([*skipped, *result.skipped]))


def searches_first(ctx: StepContext) -> bool:
    """Whether the plan step searches the user's query before planning: web sources and a short query."""
    request = ctx.record.request
    return request.sources != "files" and len(request.query.strip()) <= searching.MAX_SEARCH_CHARS


async def plan(ctx: StepContext) -> Outcome:
    request = ctx.record.request
    files = ctx.items("files.jsonl", Page)
    warnings: list[str] = []
    initial: list[Hit] = []
    filtered = 0
    if searches_first(ctx):
        found = await run_search(ctx, [Query(id="q0", text=request.query)], ctx.adapters.searcher, "plan")
        initial, warnings, filtered = found.hits, failures(found.failures), found.filtered
    ctx.store.write_artifact(ctx.run_id, "initial.jsonl", initial)
    planned = await planning.plan(
        request.query,
        initial,
        [loading.outline(page) for page in files],
        ctx.adapters.planner,
        sources=request.sources,
        max_sub_queries=ctx.settings.plan.max_sub_queries,
    )
    ctx.store.write_artifact(ctx.run_id, "plan.json", planned)
    ctx.log.emit("plan.ready", "plan", PlanReadyData(queries=planned.queries))
    return Outcome(len(planned.queries), warnings=[*warnings, *planned.warnings], filtered=filtered)


class CountedSearcher:
    """Reports `stage.progress` after each query's search; later pages of a query are not counted again."""

    def __init__(self, searcher: Searcher, log: EventLog, total: int) -> None:
        self.searcher = searcher
        self.log = log
        self.total = total
        self.done = self.failed = 0

    async def search(self, query: Query, page: int = 1) -> list[Hit]:
        if page > 1:
            return await self.searcher.search(query, page)
        try:
            return await self.searcher.search(query, page)
        except Exception:
            self.failed += 1
            raise
        finally:
            self.done += 1
            self.log.progress("search", self.done, self.total, self.failed)


async def search(ctx: StepContext) -> Outcome:
    """Round 1 searches the sub-queries (and `q0` when no initial search ran) with the initial hits.

    Later rounds search their follow-ups.
    """
    initial = ctx.items("initial.jsonl", Hit) if ctx.first else []
    searched_first = searches_first(ctx)
    queries = [query for query in ctx.round_queries() if query.id != "q0" or not searched_first]
    searcher = CountedSearcher(ctx.adapters.searcher, ctx.log, len(queries))
    result = await run_search(ctx, queries, searcher, "search", initial)
    hits = [hit.model_copy(update={"round": ctx.round.number}) for hit in result.hits]
    ctx.save("hits.jsonl", hits)
    return Outcome(len(hits), warnings=failures(result.failures), filtered=result.filtered)


async def fetch(ctx: StepContext) -> Outcome:
    """Fetch the round's hits whose URL no earlier round fetched or queued, within the round's cap."""
    state = ctx.round
    found = [hit for hit in ctx.items("hits.jsonl", Hit) if hit.round == state.number]
    hits = [hit for hit in found if normalise_url(hit.url) not in state.seen]
    state.known_pages = len({normalise_url(hit.url) for hit in found}) - len({normalise_url(hit.url) for hit in hits})
    state.seen |= {normalise_url(hit.url) for hit in hits}
    total = len(searching.merge_hits([hits]))
    done = failed = 0

    def on_item(item: Page | Skipped) -> None:
        nonlocal done, failed
        done += 1
        if isinstance(item, Page):
            source = item.source
            cached = normalise_url(source.uri) in ctx.fetcher.cached
            data = PageFetchedData(
                url=source.uri,
                source_id=source.source_id,
                title=source.title,
                chars=len(item.text),
                cached=cached,
                round=state.number,
            )
            ctx.log.emit("page.fetched", "fetch", data)
        else:
            failed += 1
            log.warning("fetch %s failed: %s", item.item, item.reason)
            ctx.log.emit("page.failed", "fetch", PageFailedData(url=item.item, reason=short_reason(item.reason)))
        ctx.log.progress("fetch", done, total, failed)

    concurrency = ctx.settings.fetch.concurrency or DEFAULT_CONCURRENCY["firecrawl"]
    left = max(ctx.settings.fetch.max_pages - state.fetched, 0)
    later = max(ctx.planned_rounds() - state.number, 0)
    cap = round_cap(left, later, ctx.settings.research.queries_per_round, ctx.settings.search.max_results)
    result = await fetching.fetch(hits, ctx.fetcher, concurrency=concurrency, max_pages=cap, on_item=on_item)
    pages = [page.model_copy(update={"round": state.number}) for page in result.pages]
    ctx.save("pages.jsonl", pages)
    state.fetched += len(pages)
    state.new_pages = len(pages)
    return Outcome(len(pages), unfetched=result.unfetched)


async def chunk(ctx: StepContext) -> Outcome:
    """Round 1 chunks every page; later rounds chunk their new pages, deduped against earlier chunks."""
    cfg = ctx.settings.chunk
    existing = [] if ctx.first else ctx.items("chunks.jsonl", Chunk)
    pages = ctx.pages() if ctx.first else [page for page in ctx.round_pages() if page.source.kind == "web"]
    result = chunking.chunk(pages, size=cfg.size_chars, overlap=cfg.overlap, min_chars=cfg.min_chars, existing=existing)
    ctx.save("chunks.jsonl", result.chunks)
    return Outcome(len(result.chunks))


async def prefilter(ctx: StepContext) -> Outcome:
    cfg = ctx.settings.prefilter
    embedder = ctx.adapters.embedder
    warnings: list[str] = []
    cache: EmbeddingMapping | None = None
    if cfg.provider == "embeddings" and embedder is not None:
        try:
            info = await embedder.describe()
            cache = EmbeddingMapping(EmbeddingCache(ctx.store.cache_dir / "embeddings"), info.model, info.dimension)
        except Exception as error:
            warnings.append(f"embedding model unknown, cache not used: {error}")
    queries = ctx.round_queries()
    pages = ctx.round_pages()
    result = await prefiltering.prefilter(
        queries,
        pages,
        ctx.round_chunks(pages),
        method=cfg.provider,
        embedder=embedder,
        top_k=cfg.top_k,
        passthrough_chars=ctx.settings.select.passthrough_chars,
        cache=cache,
    )
    ctx.save("candidates.jsonl", result.candidates)
    provider = stage_provider("prefilter", ctx.settings) if result.method == cfg.provider else result.method
    passed = {candidate.query_id for candidate in result.candidates if candidate.passthrough}
    return Outcome(
        len(result.candidates),
        provider=provider,
        warnings=[*warnings, *result.warnings],
        passthrough=[query.id for query in queries if query.id in passed],
    )


def kept_passages(report: QueryScores, chunks: dict[str, Chunk], pages: dict[str, Page]) -> list[KeptPassage]:
    kept: list[KeptPassage] = []
    for score in report.passages:
        piece = chunks[score.chunk_id]
        source = pages[piece.source_id].source
        kept.append(
            KeptPassage(
                chunk_id=piece.chunk_id,
                source_id=source.source_id,
                title=source.title,
                uri=source.uri,
                heading_path=piece.heading_path,
                text=piece.text,
                display=score.display,
            )
        )
    return kept


async def score(ctx: StepContext) -> Outcome:
    """Score the round's candidates with the scorer the last round ended on, then keep each chunk once."""
    state = ctx.round
    plan = ctx.plan()
    queries = [query for query in plan.queries if query.round == state.number]
    pages = ctx.round_pages()
    chunks = ctx.round_chunks(pages)
    chunk_of = {piece.chunk_id: piece for piece in chunks}
    page_of = {page.source.source_id: page for page in pages}
    done = 0

    def on_item(report: QueryScores) -> None:
        nonlocal done
        done += 1
        data = PassagesScoredData(
            query_id=report.query_id,
            scorer=report.scorer,
            scored=report.scored,
            kept=report.kept,
            threshold_display=report.threshold_display,
            passages=kept_passages(report, chunk_of, page_of),
        )
        ctx.log.emit("passages.scored", "score", data)
        ctx.log.progress("score", done, len(queries))

    cfg = ctx.settings.score
    if state.scorer is not None:
        cfg = cfg.model_copy(update={"provider": state.scorer})
    own = {query.id for query in queries}
    candidates = [item for item in ctx.items("candidates.jsonl", Candidate) if item.query_id in own]
    scorer = ctx.adapters.scorers.get(cfg.provider)
    result = await scoring.score(candidates, queries, pages, chunks, scorer, cfg=cfg, on_item=on_item)
    state.scorer = result.scorer
    for n, failure in enumerate(result.failed):
        following = result.failed[n + 1].item if n + 1 < len(result.failed) else result.scorer
        ctx.log.emit(
            "stage.failed", "score", StageFailedData(error=f"{failure.item}: {failure.reason}", next=following)
        )
    new = [item.model_copy(update={"round": state.number}) for item in result.scores]
    earlier = [] if ctx.first else ctx.items("scores.jsonl", Score)
    scores = scoring.keep_once([*earlier, *new], plan.queries)
    ctx.store.write_artifact(ctx.run_id, "scores.jsonl", scores)
    state.kept = sum(item.kept for item in scores[len(earlier) :])
    return Outcome(len(new), provider=result.scorer)


def selection_inputs(ctx: StepContext) -> tuple[list[Score], list[Page], list[Chunk], list[Query]]:
    return ctx.items("scores.jsonl", Score), ctx.pages(), ctx.items("chunks.jsonl", Chunk), ctx.plan().queries


def estimate(settings: Settings, text: str) -> int:
    return selecting.estimate_tokens(
        text, chars_per_token=settings.llm.chars_per_token, margin=settings.llm.token_margin
    )


def gap_budget(settings: Settings, query: str, queries: Sequence[Query]) -> int:
    """`research.gap_context_tokens`, or for `auto` the room the window leaves after the gap prompt and output."""
    tokens = settings.research.gap_context_tokens
    if tokens != "auto":
        return tokens
    return selecting.budget(
        context_window=settings.llm.context_window,
        max_context_tokens=None,
        prompt_reserve_tokens=settings.select.prompt_reserve_tokens,
        output_tokens=gapping.MAX_TOKENS,
        query_tokens=estimate(settings, query) + estimate(settings, "\n".join(item.text for item in queries)),
    )


async def gap(ctx: StepContext) -> Outcome:
    """Read the best passages so far and append the follow-up queries for the next round to the plan."""
    settings = ctx.settings
    plan = ctx.plan()
    inputs = selection_inputs(ctx)
    state = ctx.round
    known = (
        [query for query in ctx.round_queries() if query.id != "q0"] if state.number > 1 and not state.new_pages else []
    )
    selection = selecting.select(
        ctx.record.request.query,
        *inputs,
        budget_tokens=gap_budget(settings, ctx.record.request.query, plan.queries),
        max_per_source=settings.select.max_chunks_per_source,
        file_share=settings.select.file_share,
        chars_per_token=settings.llm.chars_per_token,
        margin=settings.llm.token_margin,
    )
    result = await gapping.gap(
        ctx.record.request.query,
        plan.queries,
        selection.context,
        ctx.adapters.planner,
        scores=inputs[0],
        score_cfg=settings.score,
        known=known,
        limit=settings.research.queries_per_round,
        today=date.today().isoformat(),
    )
    state.gap = result
    ctx.store.write_artifact(
        ctx.run_id, "plan.json", plan.model_copy(update={"queries": [*plan.queries, *result.queries]})
    )
    data = GapReadyData(
        round=state.number,
        queries=result.queries,
        note=result.note,
        uncovered=result.uncovered,
        retried=result.retried,
    )
    ctx.log.emit("gap.ready", "gap", data)
    return Outcome(len(result.queries))


async def select(ctx: StepContext) -> Outcome:
    settings = ctx.settings
    max_context = settings.select.max_context_tokens
    budget = selecting.budget(
        context_window=settings.llm.context_window,
        max_context_tokens=None if max_context == "auto" else max_context,
        prompt_reserve_tokens=settings.select.prompt_reserve_tokens,
        output_tokens=selecting.output_tokens(settings.write.words, settings.llm.max_output_tokens),
        query_tokens=estimate(settings, ctx.record.request.query),
    )
    selection = selecting.select(
        ctx.record.request.query,
        *selection_inputs(ctx),
        budget_tokens=budget,
        max_per_source=settings.select.max_chunks_per_source,
        file_share=settings.select.file_share,
        chars_per_token=settings.llm.chars_per_token,
        margin=settings.llm.token_margin,
    )
    ctx.store.write_artifact(ctx.run_id, "context.json", selection.context)
    ctx.store.write_artifact(ctx.run_id, "select.jsonl", selection.skipped)
    return Outcome(len(selection.context.passages))


async def write(ctx: StepContext) -> Outcome:
    context = ctx.store.read_artifact(ctx.run_id, "context.json", Context)
    ctx.store.write_text(ctx.run_id, "report.md", "")

    def on_delta(text: str) -> None:
        ctx.store.append_report(ctx.run_id, text)
        ctx.log.live("report.delta", "write", ReportTextData(text=text))

    llm = ctx.settings.llm
    sizing = writing.Sizing(
        context_window=llm.context_window,
        chars_per_token=llm.chars_per_token,
        token_margin=llm.token_margin,
        max_continuations=llm.max_continuations,
        max_output_tokens=llm.max_output_tokens,
    )
    report = await writing.write(context, ctx.settings.write, ctx.adapters.writer, sizing=sizing, on_delta=on_delta)
    ctx.store.write_text(ctx.run_id, "report.md", report.markdown)
    ctx.store.write_artifact(ctx.run_id, "report.json", report)
    return Outcome(len(report.body.strip()), warnings=list(report.warnings))


STEPS = {
    "load": load,
    "plan": plan,
    "search": search,
    "fetch": fetch,
    "chunk": chunk,
    "prefilter": prefilter,
    "score": score,
    "gap": gap,
    "select": select,
    "write": write,
}

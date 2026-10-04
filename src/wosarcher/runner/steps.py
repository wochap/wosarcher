"""One async function per stage: read inputs from earlier artifacts, call the stage, write its artifact.

Each step returns an `Outcome`; the runner turns it into `stage.done`.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from wosarcher.attachments import collect
from wosarcher.config import DEFAULT_CONCURRENCY, Settings
from wosarcher.models import (
    Attachment,
    Candidate,
    Chunk,
    Context,
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
class StepContext:
    store: RunStore
    record: RunRecord
    settings: Settings
    adapters: Adapters
    log: EventLog
    fetcher: CachedFetcher

    @property
    def run_id(self) -> str:
        return self.record.run_id

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


def short_reason(text: str) -> str:
    """The first line of an error, at most 200 characters, ending with `…` when cut."""
    lines = text.strip().splitlines()
    first = lines[0] if lines else ""
    if len(first) <= REASON_MAX_CHARS and len(lines) <= 1:
        return first
    return first[: REASON_MAX_CHARS - 1] + "…"


def failures(items: list[Skipped]) -> list[str]:
    return [f"{item.item}: {item.reason}" for item in items]


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


async def plan(ctx: StepContext) -> Outcome:
    request = ctx.record.request
    files = ctx.items("files.jsonl", Page)
    warnings: list[str] = []
    initial: list[Hit] = []
    if request.sources != "files":
        found = await searching.search(
            [Query(id="q0", text=request.query)], ctx.adapters.searcher, on_item=hit_found(ctx, "plan")
        )
        initial, warnings = found.hits, failures(found.failures)
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
    return Outcome(len(planned.queries), warnings=[*warnings, *planned.warnings])


class CountedSearcher:
    """Reports `stage.progress` after each query's search."""

    def __init__(self, searcher: Searcher, log: EventLog, total: int) -> None:
        self.searcher = searcher
        self.log = log
        self.total = total
        self.done = self.failed = 0

    async def search(self, query: Query) -> list[Hit]:
        try:
            return await self.searcher.search(query)
        except Exception:
            self.failed += 1
            raise
        finally:
            self.done += 1
            self.log.progress("search", self.done, self.total, self.failed)


async def search(ctx: StepContext) -> Outcome:
    initial = ctx.items("initial.jsonl", Hit)
    queries = ctx.plan().queries[1:]
    searcher = CountedSearcher(ctx.adapters.searcher, ctx.log, len(queries))
    result = await searching.search(queries, searcher, initial=initial, on_item=hit_found(ctx, "search"))
    ctx.store.write_artifact(ctx.run_id, "hits.jsonl", result.hits)
    return Outcome(len(result.hits), warnings=failures(result.failures))


async def fetch(ctx: StepContext) -> Outcome:
    hits = ctx.items("hits.jsonl", Hit)
    total = len(searching.merge_hits([hits]))
    done = failed = 0

    def on_item(item: Page | Skipped) -> None:
        nonlocal done, failed
        done += 1
        if isinstance(item, Page):
            source = item.source
            cached = normalise_url(source.uri) in ctx.fetcher.cached
            data = PageFetchedData(
                url=source.uri, source_id=source.source_id, title=source.title, chars=len(item.text), cached=cached
            )
            ctx.log.emit("page.fetched", "fetch", data)
        else:
            failed += 1
            log.warning("fetch %s failed: %s", item.item, item.reason)
            ctx.log.emit("page.failed", "fetch", PageFailedData(url=item.item, reason=short_reason(item.reason)))
        ctx.log.progress("fetch", done, total, failed)

    concurrency = ctx.settings.fetch.concurrency or DEFAULT_CONCURRENCY["firecrawl"]
    result = await fetching.fetch(hits, ctx.fetcher, concurrency=concurrency, on_item=on_item)
    ctx.store.write_artifact(ctx.run_id, "pages.jsonl", result.pages)
    return Outcome(len(result.pages))


async def chunk(ctx: StepContext) -> Outcome:
    cfg = ctx.settings.chunk
    result = chunking.chunk(ctx.pages(), size=cfg.size, overlap=cfg.overlap)
    ctx.store.write_artifact(ctx.run_id, "chunks.jsonl", result.chunks)
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
    plan = ctx.plan()
    result = await prefiltering.prefilter(
        plan.queries,
        ctx.pages(),
        ctx.items("chunks.jsonl", Chunk),
        method=cfg.provider,
        embedder=embedder,
        top_k=cfg.top_k,
        passthrough_chars=ctx.settings.select.passthrough_chars,
        cache=cache,
    )
    ctx.store.write_artifact(ctx.run_id, "candidates.jsonl", result.candidates)
    provider = stage_provider("prefilter", ctx.settings) if result.method == cfg.provider else result.method
    passed = {candidate.query_id for candidate in result.candidates if candidate.passthrough}
    return Outcome(
        len(result.candidates),
        provider=provider,
        warnings=[*warnings, *result.warnings],
        passthrough=[query.id for query in plan.queries if query.id in passed],
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
    queries = ctx.plan().queries
    pages = ctx.pages()
    chunks = ctx.items("chunks.jsonl", Chunk)
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
    candidates = ctx.items("candidates.jsonl", Candidate)
    scorer = ctx.adapters.scorers.get(cfg.provider)
    result = await scoring.score(candidates, queries, pages, chunks, scorer, cfg=cfg, on_item=on_item)
    for n, failure in enumerate(result.failed):
        following = result.failed[n + 1].item if n + 1 < len(result.failed) else result.scorer
        ctx.log.emit(
            "stage.failed", "score", StageFailedData(error=f"{failure.item}: {failure.reason}", next=following)
        )
    ctx.store.write_artifact(ctx.run_id, "scores.jsonl", result.scores)
    return Outcome(len(result.scores), provider=result.scorer)


async def select(ctx: StepContext) -> Outcome:
    settings = ctx.settings
    budget = selecting.budget(
        context_window=settings.llm.context_window,
        max_context_tokens=settings.select.max_context_tokens,
        prompt_reserve_tokens=settings.select.prompt_reserve_tokens,
        words=settings.write.words,
    )
    context = selecting.select(
        ctx.record.request.query,
        ctx.items("scores.jsonl", Score),
        ctx.pages(),
        ctx.items("chunks.jsonl", Chunk),
        ctx.plan().queries,
        budget_tokens=budget,
        max_per_source=settings.select.max_chunks_per_source,
        file_share=settings.select.file_share,
        chars_per_token=settings.llm.chars_per_token,
        margin=settings.llm.token_margin,
    )
    ctx.store.write_artifact(ctx.run_id, "context.json", context)
    return Outcome(len(context.passages))


async def write(ctx: StepContext) -> Outcome:
    context = ctx.store.read_artifact(ctx.run_id, "context.json", Context)
    ctx.store.write_text(ctx.run_id, "report.md", "")

    def on_delta(text: str) -> None:
        ctx.store.append_report(ctx.run_id, text)
        ctx.log.live("report.delta", "write", ReportTextData(text=text))

    report = await writing.write(context, ctx.settings.write, ctx.adapters.writer, on_delta=on_delta)
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
    "select": select,
    "write": write,
}

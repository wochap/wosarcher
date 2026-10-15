"""The catalog run: `draft`, then `expand`, `search`, `fetch`, `chunk`, `extract` once per wave, then `assemble`.

`nodes.jsonl` is the frontier and the checkpoint. A resumed run sets every
`expanding` node back to `discovered`, drops the interrupted wave's hits and
queries, keeps the pages already fetched, and continues with the next wave.
A fork from `extract` runs one extraction pass over every node with its
recorded pages, with `expand`, `search`, `fetch`, and `chunk` skipped.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from wosarcher.models import (
    WAVE_STAGES,
    CatalogDone,
    CatalogDoneData,
    CatalogRecord,
    CatalogStopReason,
    Chunk,
    ExtractedRecord,
    Hit,
    Node,
    NodeExtractedData,
    NodeFailedData,
    NodeFoundData,
    Page,
    PageFailedData,
    PageFetchedData,
    Plan,
    Query,
    Skipped,
    Stage,
    StageDoneData,
    Structure,
    StructureFieldInfo,
    StructureReadyData,
    WaveDone,
    WaveDoneData,
    WaveEntry,
    normalise_url,
    parse_node_query_id,
)
from wosarcher.runner import steps
from wosarcher.stages import assemble as assembling
from wosarcher.stages import chunk as chunking
from wosarcher.stages import draft as drafting
from wosarcher.stages import expand as expanding
from wosarcher.stages import extract as extracting
from wosarcher.stages import fetch as fetching
from wosarcher.stages import load as loading
from wosarcher.stages.extract import Child, Extracted, NodePages, Sizing

if TYPE_CHECKING:
    from wosarcher.runner import Runner

Step = Callable[["CatalogContext"], Awaitable[steps.Outcome]]


@dataclass
class WaveState:
    """The wave loop's bookkeeping; counters are the current wave's."""

    number: int = 1
    nodes: list[Node] = field(default_factory=list[Node])
    expanded: int = 0
    found: int = 0
    records: int = 0
    failed: int = 0
    attempts: int = 0
    """Extraction calls made this wave."""
    dropped: int = 0
    """Children not added for lack of room under `max_nodes`."""
    first_failure: str | None = None
    fetched: int = 0
    """Counted pages across all waves."""
    seen: dict[str, str] = field(default_factory=dict[str, str])
    """Normalised URL to the source ID of the page fetched for it."""
    expansion: expanding.ExpandResult | None = None
    hits: list[Hit] = field(default_factory=list[Hit])
    reason: CatalogStopReason | None = None
    re_extract: bool = False

    def next(self) -> None:
        self.number += 1
        self.expanded = self.found = self.records = self.failed = self.attempts = self.dropped = 0
        self.first_failure = None
        self.expansion = None
        self.hits = []

    def entry(self) -> WaveEntry:
        return WaveEntry(
            wave=self.number,
            expanded=self.expanded,
            found=self.found,
            records=self.records,
            failed=self.failed,
            dropped=self.dropped,
        )


@dataclass
class CatalogContext(steps.StepContext):
    wave: WaveState = field(default_factory=WaveState)

    def structure(self) -> Structure:
        return self.store.read_artifact(self.run_id, "structure.json", Structure)

    def save_nodes(self) -> None:
        self.store.write_artifact(self.run_id, "nodes.jsonl", self.wave.nodes)

    def replace(self, node: Node) -> None:
        nodes = self.wave.nodes
        position = next(n for n, item in enumerate(nodes) if item.id == node.id)
        nodes[position] = node

    def found(self, node: Node, stage: Stage) -> None:
        data = NodeFoundData(
            node_id=node.id,
            name=node.name,
            type=node.type,
            parent_id=node.parent_id,
            depth=node.depth,
            url=node.url,
            wave=node.wave,
            found_by=node.found_by,
        )
        self.log.emit("node.found", stage, data)

    def fail(self, node: Node, reason: str, stage: Stage) -> None:
        self.replace(node.model_copy(update={"status": "failed", "reason": reason}))
        self.wave.failed += 1
        self.wave.first_failure = self.wave.first_failure or reason
        self.log.emit("node.failed", stage, NodeFailedData(node_id=node.id, reason=reason))


def wave_entries(ctx: CatalogContext) -> list[WaveEntry]:
    """One entry per wave from the `wave.done` events, the last one of a wave winning."""
    entries: dict[int, WaveEntry] = {}
    for event in ctx.store.read_events(ctx.run_id):
        if isinstance(event, WaveDone):
            entries[event.data.wave] = WaveEntry(**event.data.model_dump())
    return [entries[number] for number in sorted(entries)]


def restart(ctx: CatalogContext) -> None:
    """Reload the frontier: `expanding` nodes back to `discovered`, the next wave's hits and queries dropped."""
    state = ctx.wave
    nodes = ctx.store.read_items(ctx.run_id, "nodes.jsonl", Node)
    state.nodes = [
        node.model_copy(update={"status": "discovered", "pages": []}) if node.status == "expanding" else node
        for node in nodes
    ]
    last = max((entry.wave for entry in wave_entries(ctx)), default=0)
    state.re_extract = ctx.record.fork_from == "extract"
    state.number = max(last, 1) if state.re_extract else last + 1
    extracted = {node.id for node in state.nodes if node.status == "extracted"}
    records = ctx.store.read_items(ctx.run_id, "records.jsonl", ExtractedRecord)
    ctx.store.write_artifact(ctx.run_id, "records.jsonl", [item for item in records if item.node_id in extracted])
    if not state.re_extract:
        hits = ctx.store.read_items(ctx.run_id, "hits.jsonl", Hit)
        ctx.store.write_artifact(ctx.run_id, "hits.jsonl", [hit for hit in hits if hit.round < state.number])
        plan = ctx.plan()
        kept = [query for query in plan.queries if query.round < state.number]
        ctx.store.write_artifact(ctx.run_id, "plan.json", plan.model_copy(update={"queries": kept}))
    pages = ctx.store.read_items(ctx.run_id, "pages.jsonl", Page)
    state.seen = {normalise_url(page.source.uri): page.source.source_id for page in pages}
    state.fetched = len(pages)
    ctx.save_nodes()


def stop_rule(ctx: CatalogContext) -> CatalogStopReason | None:
    state = ctx.wave
    structure = ctx.structure()
    if state.attempts > 0 and state.records == 0:
        return "extract failed"
    if not any(node.status == "discovered" for node in state.nodes):
        return "max nodes" if len(state.nodes) >= structure.limits.max_nodes else "frontier empty"
    if state.fetched >= ctx.settings.fetch.max_pages:
        return "page limit reached"
    return None


async def run_stages(runner: "Runner", ctx: CatalogContext, todo: Sequence[Stage], until: Stage | None) -> None:
    """Every unfinished catalog stage in order; the wave stages as one loop."""
    looped = False
    for stage in todo:
        runner.current = stage
        if stage in WAVE_STAGES:
            if looped:
                continue
            looped = True
            if await waves(runner, ctx, until):
                return
            continue
        if stage == "load" and ctx.record.request.sources == "web":
            runner.skip(ctx, stage)
            continue
        ctx.round.number = ctx.log.round = 1
        await runner.run_stage(ctx, stage, CATALOG_STEPS[stage])


async def waves(runner: "Runner", ctx: CatalogContext, until: Stage | None) -> bool:
    """Run waves until a stop rule holds; true when `until` stopped the run inside the loop."""
    restart(ctx)
    state = ctx.wave
    while True:
        if not any(node.status == "discovered" for node in state.nodes):
            state.reason = stop_rule(ctx)
            break
        state.nodes = [
            node.model_copy(update={"status": "expanding"}) if node.status == "discovered" else node
            for node in state.nodes
        ]
        state.expanded = sum(node.status == "expanding" for node in state.nodes)
        ctx.save_nodes()
        ctx.round.number = ctx.log.round = state.number
        for stage in WAVE_STAGES:
            runner.current = stage
            if state.re_extract and stage != "extract":
                data = StageDoneData(count=0, seconds=0, skipped=True, round=state.number)
                ctx.log.emit("stage.done", stage, data)
                continue
            await runner.run_stage(ctx, stage, CATALOG_STEPS[stage])
            if stage == until:
                return True
        if state.re_extract:
            state.reason = stop_rule(ctx) or "frontier empty"
            break
        ctx.log.emit("wave.done", "extract", WaveDoneData(**state.entry().model_dump()))
        state.reason = stop_rule(ctx)
        if state.reason is not None:
            break
        state.next()
    if state.reason == "extract failed":
        runner.warnings.append(f"extract failed: {state.first_failure}")
    return False


# Steps


async def draft(ctx: CatalogContext) -> steps.Outcome:
    request = ctx.record.request
    outlines = [loading.outline(page) for page in ctx.items("files.jsonl", Page)]
    result = await drafting.draft(
        request.query,
        request.structure,
        outlines,
        ctx.adapters.draft_llm,
        catalog=ctx.settings.catalog,
        today=date.today().isoformat(),
        effort=ctx.settings.llm.reasoning.draft,
    )
    structure = result.structure
    run_id = ctx.run_id
    ctx.store.write_artifact(run_id, "structure.json", structure)
    ctx.store.write_artifact(run_id, "nodes.jsonl", result.nodes)
    ctx.store.write_artifact(run_id, "plan.json", Plan(queries=[]))
    for name in ("hits.jsonl", "pages.jsonl", "chunks.jsonl", "records.jsonl"):
        ctx.store.write_text(run_id, name, "")
    if result.derived:
        ctx.record = ctx.record.model_copy(update={"request": request.model_copy(update={"structure": structure})})
        ctx.store.write_artifact(run_id, "request.json", ctx.record)
    data = StructureReadyData(
        fields=[StructureFieldInfo(name=item.name, type=item.type) for item in structure.fields],
        seeds=len(structure.seeds),
        relation=structure.relation,
        limits=structure.limits,
        derived=result.derived,
    )
    ctx.log.emit("structure.ready", "draft", data)
    for node in result.nodes:
        ctx.found(node, "draft")
    return steps.Outcome(len(result.nodes))


def wave_nodes(ctx: CatalogContext) -> list[tuple[int, Node]]:
    """The wave's nodes with their discovery index (1-based)."""
    return [(n, node) for n, node in enumerate(ctx.wave.nodes, start=1) if node.status == "expanding"]


async def expand(ctx: CatalogContext) -> steps.Outcome:
    state = ctx.wave
    result = expanding.expand(wave_nodes(ctx), ctx.structure(), state.number)
    state.expansion = result
    plan = ctx.plan()
    ctx.store.write_artifact(
        ctx.run_id, "plan.json", plan.model_copy(update={"queries": [*plan.queries, *result.queries]})
    )
    return steps.Outcome(len(result.queries))


async def search(ctx: CatalogContext) -> steps.Outcome:
    state = ctx.wave
    queries: list[Query] = state.expansion.queries if state.expansion else []
    if not queries:
        state.hits = []
        return steps.Outcome(0)
    searcher = steps.CountedSearcher(ctx.adapters.searcher, ctx.log, len(queries))
    result = await steps.run_search(ctx, queries, searcher, "search")
    state.hits = [hit.model_copy(update={"round": state.number}) for hit in result.hits]
    ctx.store.append_jsonl(ctx.run_id, "hits.jsonl", state.hits)
    return steps.Outcome(len(state.hits), warnings=steps.failures(result.failures), filtered=result.filtered)


def candidates(state: WaveState, item: expanding.NodeExpansion) -> list[str]:
    """The node's URLs in fetch order: known URL, children hits by rank, self hits by rank; no repeats."""
    by_kind: dict[str, list[Hit]] = {"c": [], "s": []}
    for hit in state.hits:
        for query_id in hit.query_ids:
            parsed = parse_node_query_id(query_id)
            if parsed is not None and parsed[0] == item.index:
                by_kind[parsed[1]].append(hit)
    urls = [item.url] if item.url else []
    urls += [hit.url for kind in ("c", "s") for hit in sorted(by_kind[kind], key=lambda hit: hit.rank)]
    return list({normalise_url(url): url for url in reversed(urls)}.values())[::-1]


async def fetch(ctx: CatalogContext) -> steps.Outcome:
    """Per node at most `pages_per_node` pages; a URL fetched earlier in the run is reused without a fetch."""
    state = ctx.wave
    settings = ctx.settings
    per_node = ctx.structure().limits.pages_per_node
    plans = state.expansion.nodes if state.expansion else []
    queue = {item.node_id: candidates(state, item) for item in plans}
    pages: dict[str, list[str]] = {item.node_id: [] for item in plans}
    failed: set[str] = set()
    new: list[Page] = []
    unfetched = 0
    min_chars = settings.chunk.min_chars
    done = failures = total = 0

    def on_item(item: Page | Skipped) -> None:
        nonlocal done, failures
        done += 1
        if isinstance(item, Page):
            source = item.source
            data = PageFetchedData(
                url=source.uri,
                source_id=source.source_id,
                title=source.title,
                chars=len(item.text),
                cached=normalise_url(source.uri) in ctx.fetcher.cached,
                thin=fetching.is_thin(item, min_chars),
                round=state.number,
            )
            ctx.log.emit("page.fetched", "fetch", data)
        else:
            failures += 1
            reason = steps.short_reason(item.reason)
            ctx.log.emit("page.failed", "fetch", PageFailedData(url=item.item, reason=reason))
        ctx.log.progress("fetch", done, total, failures)

    while True:
        wanted: dict[str, str] = {}
        waiting: dict[str, list[str]] = {}
        for node_id, urls in queue.items():
            pending = 0
            while urls and len(pages[node_id]) + pending < per_node:
                url = urls.pop(0)
                key = normalise_url(url)
                if key in failed:
                    continue
                if key in state.seen:
                    if state.seen[key] not in pages[node_id]:
                        pages[node_id].append(state.seen[key])
                    continue
                wanted.setdefault(key, url)
                waiting.setdefault(key, []).append(node_id)
                pending += 1
        if not wanted:
            break
        left = max(settings.fetch.max_pages - state.fetched, 0)
        total += len(wanted)
        hits = [
            Hit(url=url, title=url, snippet="", rank=1, query_ids=[f"u{n}"]) for n, url in enumerate(wanted.values())
        ]
        concurrency = settings.fetch.concurrency or steps.DEFAULT_CONCURRENCY["firecrawl"]
        result = await fetching.fetch(
            hits, ctx.fetcher, concurrency=concurrency, max_pages=left, min_chars=min_chars, on_item=on_item
        )
        state.fetched += result.counted
        unfetched += result.unfetched
        keys = list(wanted)
        for page in result.pages:
            key = keys[int(page.query_ids[0][1:])]
            source_id = page.source.source_id
            state.seen[key] = state.seen.setdefault(normalise_url(page.source.uri), source_id)
            new.append(page.model_copy(update={"round": state.number, "query_ids": [], "rank": 0}))
        for key, node_ids in waiting.items():
            if key not in state.seen:
                failed.add(key)
                continue
            for node_id in node_ids:
                if state.seen[key] not in pages[node_id]:
                    pages[node_id].append(state.seen[key])
        if left == 0 or result.unfetched:
            break
    ctx.store.append_jsonl(ctx.run_id, "pages.jsonl", new)
    for node in [node for node in state.nodes if node.id in pages]:
        if pages[node.id]:
            ctx.replace(node.model_copy(update={"pages": pages[node.id]}))
        else:
            ctx.fail(node, "no page", "fetch")
    ctx.save_nodes()
    return steps.Outcome(len(new), unfetched=unfetched)


async def chunk(ctx: CatalogContext) -> steps.Outcome:
    """Chunk the pages that have no chunk yet: this wave's new pages, and any an interrupted wave left."""
    cfg = ctx.settings.chunk
    chunked = {piece.source_id for piece in ctx.items("chunks.jsonl", Chunk)}
    pages = [page for page in ctx.items("pages.jsonl", Page) if page.source.source_id not in chunked]
    result = chunking.chunk(pages, size=cfg.size_chars, overlap=cfg.overlap, min_chars=cfg.min_chars)
    ctx.store.append_jsonl(ctx.run_id, "chunks.jsonl", result.chunks)
    return steps.Outcome(len(result.chunks))


def add_children(ctx: CatalogContext, parent: Node, children: Sequence[Child]) -> bool:
    """Add new children as nodes; false when some were dropped for lack of room under `max_nodes`."""
    state = ctx.wave
    structure = ctx.structure()
    by_name = {assembling.normalised_name(node.name): node.id for node in state.nodes}
    by_url = {normalise_url(node.url): node.id for node in state.nodes if node.url}
    taken = {node.id for node in state.nodes}
    complete = True
    for child in children:
        existing_id = by_name.get(assembling.normalised_name(child.name)) or (
            by_url.get(normalise_url(child.url)) if child.url else None
        )
        if existing_id is not None:
            existing = next(node for node in state.nodes if node.id == existing_id)
            flag = f"parent: also listed under {parent.name}"
            other = existing.parent_id is not None and existing.parent_id != parent.id and existing.id != parent.id
            if other and flag not in existing.flags:
                ctx.replace(existing.model_copy(update={"flags": [*existing.flags, flag]}))
            continue
        if len(state.nodes) >= structure.limits.max_nodes:
            state.dropped += 1
            complete = False
            continue
        flags: list[str] = []
        kind = child.type
        if kind not in structure.types:
            flags.append(f"type: {kind or 'none'} not in the structure")
            kind = structure.types[0]
        node = Node(
            id=assembling.unique_slug(child.name, taken),
            name=child.name,
            type=kind,
            parent_id=parent.id,
            depth=parent.depth + 1,
            url=child.url,
            wave=state.number,
            found_by="links" if child.url else "search",
            flags=flags,
        )
        state.nodes.append(node)
        by_name[assembling.normalised_name(node.name)] = node.id
        if node.url:
            by_url[normalise_url(node.url)] = node.id
        state.found += 1
        ctx.found(node, "extract")
    return complete


async def extract(ctx: CatalogContext) -> steps.Outcome:
    state = ctx.wave
    settings = ctx.settings
    structure = ctx.structure()
    page_of = {page.source.source_id: page for page in ctx.items("pages.jsonl", Page)}
    chunks_of: dict[str, list[Chunk]] = {}
    for piece in ctx.items("chunks.jsonl", Chunk):
        chunks_of.setdefault(piece.source_id, []).append(piece)
    names = {node.id: node.name for node in state.nodes}
    items: list[NodePages] = []
    for _, node in wave_nodes(ctx):
        pages = [page_of[source_id] for source_id in node.pages if source_id in page_of]
        if not pages:
            ctx.fail(node, "no page", "extract")
            continue
        expandable = not state.re_extract and structure.is_expandable(node.type, node.depth)
        parent = names.get(node.parent_id) if node.parent_id else None
        items.append(
            NodePages(node, parent, [(page, chunks_of.get(page.source.source_id, [])) for page in pages], expandable)
        )
    expandable_ids = {item.node.id for item in items if item.expandable}

    def on_item(found: Extracted) -> None:
        state.attempts += 1
        node = next(node for node in state.nodes if node.id == found.node_id)
        if found.record is None:
            ctx.fail(node, found.reason or "extract failed", "extract")
            ctx.save_nodes()
            return
        ctx.store.append_jsonl(ctx.run_id, "records.jsonl", [found.record])
        ctx.replace(node.model_copy(update={"status": "extracted", "reason": None}))
        state.records += 1
        data = NodeExtractedData(
            node_id=node.id,
            record=found.record.record,
            sources=found.record.sources,
            flags=found.record.flags,
            children=len(found.children),
        )
        ctx.log.emit("node.extracted", "extract", data)
        if node.id in expandable_ids:
            complete = add_children(ctx, node, found.children)
            current = next(item for item in state.nodes if item.id == node.id)
            ctx.replace(current.model_copy(update={"expanded": complete}))
        ctx.save_nodes()
        ctx.log.progress("extract", state.attempts, len(items), state.failed)

    tokens = settings.catalog.context_tokens
    sizing = Sizing(
        context_tokens=None if tokens == "auto" else tokens,
        context_window=settings.llm.context_window,
        prompt_reserve_tokens=settings.select.prompt_reserve_tokens,
        chars_per_token=settings.llm.chars_per_token,
        token_margin=settings.llm.token_margin,
    )
    await extracting.extract(
        items,
        structure,
        ctx.adapters.extract_llm,
        concurrency=settings.catalog.concurrency,
        max_children=settings.catalog.max_children,
        today=date.today().isoformat(),
        sizing=sizing,
        effort=settings.llm.reasoning.extract,
        on_item=on_item,
    )
    ctx.save_nodes()
    return steps.Outcome(state.records)


async def assemble(ctx: CatalogContext) -> steps.Outcome:
    state = ctx.wave
    structure = ctx.structure()
    nodes = ctx.store.read_items(ctx.run_id, "nodes.jsonl", Node)
    waves = wave_entries(ctx)
    reason = state.reason
    last = state.number if reason is not None else max((entry.wave for entry in waves), default=1)
    if reason is None:
        done = ctx.store.catalog_done(ctx.run_id)
        reason = done.data.reason if isinstance(done, CatalogDone) else "frontier empty"
    note = assembling.stop_note(
        reason, wave=last, structure=structure, nodes=nodes, max_pages=ctx.settings.fetch.max_pages
    )
    records = ctx.store.read_items(ctx.run_id, "records.jsonl", ExtractedRecord)
    catalog: CatalogRecord = assembling.assemble(structure, nodes, records, waves=waves, reason=reason, note=note)
    ctx.store.write_artifact(ctx.run_id, "catalog.json", catalog)
    flagged = sum(1 for record in catalog.records if record.get("flags"))
    data = CatalogDoneData(
        waves=len(waves), nodes=len(nodes), records=len(catalog.records), flagged=flagged, reason=reason, note=note
    )
    ctx.log.emit("catalog.done", "assemble", data)
    return steps.Outcome(len(catalog.records))


CATALOG_STEPS: dict[Stage, Step] = {
    "load": steps.load,
    "draft": draft,
    "expand": expand,
    "search": search,
    "fetch": fetch,
    "chunk": chunk,
    "extract": extract,
    "assemble": assemble,
}

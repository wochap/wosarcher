"""`wosarcherd run` and `wosarcherd fork`: the engine the server spawns for each run.

Exit status: 0 done, 1 failed, 130 cancelled, 2 invalid arguments or configuration.

The process holds the run lock (`<run>/.lock`) from the moment the run
directory exists until it exits, so every reader can tell it is alive. The
server passes the run ID it chose (`--run-id`) and the run's origin
(`--origin`, `--token-name`). Run directly, the engine is not queued or
counted by any server.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from collections.abc import Callable
from contextlib import ExitStack
from typing import Annotated, Any, Literal, cast, get_args

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markdown import Markdown

import wosarcher.build as building
from wosarcher.cli.logs import stderr_listener
from wosarcher.cli.options import (
    AllowDomainOption,
    AttachOption,
    BlockDomainOption,
    ContextTokensOption,
    ContextWindowOption,
    DepthOption,
    FormatOption,
    FromOption,
    GapContextTokensOption,
    GapThinkingOption,
    JsonOption,
    LanguageOption,
    MarkerOption,
    MaxOutputOption,
    ModelOption,
    PagesOption,
    PassagesOption,
    PlanThinkingOption,
    ProfileOption,
    QueriesPerRoundOption,
    ResultsOption,
    RoundsOption,
    SearchLanguageOption,
    SetOption,
    SourcesOption,
    StyleOption,
    SubQueriesOption,
    ToneInstructionsOption,
    ToneOption,
    UntilOption,
    UseOption,
    WordsOption,
    WriteThinkingOption,
    fail,
    sources_option,
    stage_option,
    use_map,
)
from wosarcher.cli.progress import ProgressView
from wosarcher.config import (
    BLOCKS,
    LLM_KEYS,
    RESEARCH_KEYS,
    ConfigError,
    Prices,
    Resolved,
    Settings,
    catalog_structure,
    fork_settings,
    resolve_run,
    resolve_server,
    select_profile,
    use_overrides,
    without_use,
)
from wosarcher.http import UsageLedger
from wosarcher.models import (
    CATALOG_STAGES,
    CatalogRecord,
    Context,
    Origin,
    Report,
    RunCreate,
    RunFailed,
    RunKind,
    RunOutput,
    RunRecord,
    RunRequest,
    Stage,
    Structure,
)
from wosarcher.runner import Runner
from wosarcher.runner.events import Listener
from wosarcher.store import RunStore, RunStoreError

Status = Literal["done", "failed", "cancelled"]
EXIT: dict[Status, int] = {"done": 0, "failed": 1, "cancelled": 130}

RunIdOption = Annotated[str | None, typer.Option("--run-id", help="Create the run under this ID.")]
OriginOption = Annotated[str, typer.Option("--origin", hidden=True)]
TokenNameOption = Annotated[str | None, typer.Option("--token-name", hidden=True)]
FormOption = Annotated[str | None, typer.Option("--form", hidden=True, help="The API request as JSON.")]
KindOption = Annotated[str, typer.Option("--kind", help="Run kind: research or catalog.")]
StructureOption = Annotated[
    str | None, typer.Option("--structure", help="The catalog structure as JSON; absent: the draft stage derives one.")
]
MaxDepthOption = Annotated[int | None, typer.Option("--max-depth", help="Catalog limit: deepest node level.")]
MaxNodesOption = Annotated[int | None, typer.Option("--max-nodes", help="Catalog limit: nodes in the run.")]
PagesPerNodeOption = Annotated[int | None, typer.Option("--pages-per-node", help="Catalog limit: pages per node.")]


def catalog_limits(max_depth: int | None, max_nodes: int | None, pages_per_node: int | None) -> dict[str, int]:
    found = {"max_depth": max_depth, "max_nodes": max_nodes, "pages_per_node": pages_per_node}
    return {name: value for name, value in found.items() if value is not None}


def limit_overrides(limits: dict[str, int]) -> list[str]:
    """The limit flags as `catalog.<limit>` overrides."""
    return [f"catalog.{name}={value}" for name, value in limits.items()]


def catalog_request(
    kind: str, structure: str | None, limits: dict[str, int], settings: Settings, sources: str, depth: str | None
) -> Structure | None:
    """The run's structure: the JSON with the limit flags over it and the `catalog` block under it."""
    if kind not in get_args(RunKind):
        raise fail(f"--kind must be one of: {', '.join(get_args(RunKind))}", 2)
    if kind == "research":
        if structure is not None or limits:
            raise fail("--structure and the limit flags are only for --kind catalog", 2)
        return None
    if sources == "files":
        raise fail("sources: a catalog run cannot use --sources files", 2)
    if depth:
        raise fail("--depth is not for catalog runs", 2)
    if structure is None:
        return None
    try:
        data = json.loads(structure)
        if not isinstance(data, dict):
            raise ValueError("--structure must be a JSON object")
        given = cast(dict[str, Any], data)
        given["limits"] = {**cast(dict[str, Any], given.get("limits") or {}), **limits}
        return catalog_structure(given, settings.catalog)
    except (ValueError, ValidationError) as error:
        raise fail(f"--structure: {error}", 2) from None


def writing_overrides(**fields: str | int | None) -> list[str]:
    """Writing flags as `write.<field>=<value>`, appended after `--set` so they win."""
    return [f"write.{name}={json.dumps(value)}" for name, value in fields.items() if value is not None]


def research_overrides(**fields: int | str | None) -> list[str]:
    """Research flags as `--set` on their keys (`RESEARCH_KEYS`), appended after `--set` so they win."""
    return [f"{RESEARCH_KEYS[name]}={value}" for name, value in fields.items() if value is not None]


def domain_overrides(allow: list[str] | None, block: list[str] | None) -> list[str]:
    """Domain flags as JSON-list overrides of `search.allow_domains` and `search.block_domains`."""
    lists = {"search.allow_domains": allow, "search.block_domains": block}
    return [f"{key}={json.dumps(value)}" for key, value in lists.items() if value]


def language_overrides(language: str | None) -> list[str]:
    """`--search-language` as a quoted `search.language` override."""
    return [] if language is None else [f"search.language={json.dumps(language)}"]


def llm_overrides(model: str | None, limits: dict[str, int | str | None], **reasoning: str | None) -> list[str]:
    """`--model`, the limit and budget flags (`LLM_KEYS`), and the thinking flags as overrides."""
    found = [] if model is None else [f"llm.model={json.dumps(model)}"]
    found += [f"{LLM_KEYS[name]}={value}" for name, value in limits.items() if value is not None]
    return [*found, *(f"llm.reasoning.{step}={json.dumps(level)}" for step, level in reasoning.items() if level)]


def checked(make: Callable[[], Resolved]) -> Resolved:
    try:
        resolved = make()
        building.check_providers(resolved.settings)
    except (ConfigError, ValueError) as error:
        raise fail(error, 2) from None
    return resolved


def ledger_for(settings: Settings) -> UsageLedger:
    prices: dict[str, Prices] = {getattr(settings, b).provider: getattr(settings, b).prices for b in BLOCKS}
    return UsageLedger(prices)


async def execute(
    store: RunStore, settings: Settings, run_id: str, until: Stage | None, listeners: list[Listener]
) -> Status:
    """Run in a task that SIGTERM and SIGINT cancel; return the run's status."""
    async with httpx.AsyncClient() as http:
        ledger = ledger_for(settings)
        runner = Runner(store, settings, building.build(settings, http, ledger), ledger, listeners)
        task = asyncio.create_task(runner.run(run_id, until))
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, task.cancel)
        try:
            return await task
        except asyncio.CancelledError:
            return "cancelled"
        finally:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)


def diagnostics(view_shown: bool) -> list[Listener]:
    """Log lines on standard error when no progress view is shown; otherwise nothing may print under the view."""
    logger = logging.getLogger("wosarcher")
    logger.handlers.clear()
    logger.propagate = not view_shown
    if view_shown:
        logger.addHandler(logging.NullHandler())
        return []
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return [stderr_listener(logger)]


def origin_option(origin: str, token_name: str | None) -> tuple[Origin, str | None]:
    if origin not in get_args(Origin):
        raise fail(f"--origin must be one of: {', '.join(get_args(Origin))}", 2)
    return origin, token_name if origin == "api" else None  # pyright: ignore[reportReturnType]


def start(store: RunStore, settings: Settings, record: RunRecord, until: Stage | None, as_json: bool) -> None:
    err = Console(stderr=True)
    with ExitStack() as stack:
        listeners: list[Listener] = []
        if err.is_terminal and not as_json:
            listeners.append(stack.enter_context(ProgressView(err, settings.research.rounds, record.kind)))
        listeners.extend(diagnostics(view_shown=bool(listeners)))
        status = asyncio.run(execute(store, settings, record.run_id, until, listeners))
    output(store, record.run_id, status, as_json)
    raise typer.Exit(EXIT[status])


def output(store: RunStore, run_id: str, status: Status, as_json: bool) -> None:
    finished = store.finished_stages(run_id)
    error = next((e.data.error for e in reversed(store.read_events(run_id)) if isinstance(e, RunFailed)), None)
    run_dir = store.run_dir(run_id)
    catalog = (run_dir / "catalog.json").is_file()
    context = (
        store.read_artifact(run_id, "context.json", Context)
        if "select" in finished and (run_dir / "context.json").is_file()
        else None
    )
    has_report = "write" in finished and (run_dir / "report.json").is_file()
    report = store.read_artifact(run_id, "report.json", Report) if has_report else None
    if as_json:
        result = RunOutput(
            run_id=run_id, status=status, error=error if status == "failed" else None, context=context, report=report
        )
        typer.echo(result.model_dump_json(indent=2))
        return
    err = Console(stderr=True, highlight=False)
    if catalog and report is None:
        found = store.read_artifact(run_id, "catalog.json", CatalogRecord)
        typer.echo(json.dumps(found.records, indent=2, ensure_ascii=False))
    if status != "done":
        err.print(f"run {run_id} {status}" + (f": {error}" if error else ""), markup=False)
    if report is not None:
        text = (store.run_dir(run_id) / "report.md").read_text(encoding="utf-8")
        out = Console()
        if out.is_terminal:
            out.print(Markdown(text))
        else:
            typer.echo(text, nl=False)
    elif context is not None:
        typer.echo(
            f"{len(context.passages)} passages from {len(context.sources)} sources ({context.used_tokens} tokens)"
        )
        for source in context.sources:
            typer.echo(f"- {source.title} <{source.uri}>")
    err.print(f"run directory: {store.run_dir(run_id)}", markup=False)


def run(
    query: Annotated[str, typer.Argument(help="The research question.")],
    attach: AttachOption = None,
    sources: SourcesOption = "both",
    until: UntilOption = None,
    profile: ProfileOption = None,
    use: UseOption = None,
    depth: DepthOption = None,
    set_: SetOption = None,
    tone: ToneOption = None,
    tone_instructions: ToneInstructionsOption = None,
    words: WordsOption = None,
    language: LanguageOption = None,
    citation_marker: MarkerOption = None,
    reference_style: StyleOption = None,
    format_: FormatOption = None,
    sub_queries: SubQueriesOption = None,
    results_per_query: ResultsOption = None,
    max_pages: PagesOption = None,
    passages_per_query: PassagesOption = None,
    context_tokens: ContextTokensOption = None,
    gap_context_tokens: GapContextTokensOption = None,
    rounds: RoundsOption = None,
    queries_per_round: QueriesPerRoundOption = None,
    search_language: SearchLanguageOption = None,
    allow_domain: AllowDomainOption = None,
    block_domain: BlockDomainOption = None,
    model: ModelOption = None,
    context_window: ContextWindowOption = None,
    max_output: MaxOutputOption = None,
    plan_thinking: PlanThinkingOption = None,
    gap_thinking: GapThinkingOption = None,
    write_thinking: WriteThinkingOption = None,
    kind: KindOption = "research",
    structure: StructureOption = None,
    max_depth: MaxDepthOption = None,
    max_nodes: MaxNodesOption = None,
    pages_per_node: PagesPerNodeOption = None,
    run_id: RunIdOption = None,
    as_json: JsonOption = False,
    origin: OriginOption = "cli",
    token_name: TokenNameOption = None,
    form: FormOption = None,
) -> None:
    """Research QUERY in this process and write the run directory (or stop early with --until)."""
    stop = stage_option(until)
    chosen = sources_option(sources, attach)
    flags = writing_overrides(
        tone=tone,
        tone_instructions=tone_instructions,
        words=words,
        language=language,
        citation_marker=citation_marker,
        reference_style=reference_style,
        format=format_,
    )
    research = research_overrides(
        sub_queries=sub_queries,
        results_per_query=results_per_query,
        max_pages=max_pages,
        passages_per_query=passages_per_query,
        rounds=rounds,
        queries_per_round=queries_per_round,
    )
    domains = [*domain_overrides(allow_domain, block_domain), *language_overrides(search_language)]
    limits: dict[str, int | str | None] = {
        "context_window": context_window,
        "max_output_tokens": max_output,
        "context_tokens": context_tokens,
        "gap_context_tokens": gap_context_tokens,
    }
    thinking = llm_overrides(model, limits, plan=plan_thinking, gap=gap_thinking, write=write_thinking)
    caps = catalog_limits(max_depth, max_nodes, pages_per_node)
    overrides = [
        *(set_ or []),
        *flags,
        *research,
        *domains,
        *thinking,
        *limit_overrides(caps),
        *use_overrides(use_map(use)),
    ]
    env = os.environ
    settings, entries = checked(lambda: resolve_run(profile, overrides, env, depth))
    found = catalog_request(kind, structure, caps, settings, chosen, depth)
    if kind == "catalog" and stop is not None and stop not in CATALOG_STAGES:
        raise fail(f"--until {stop} is not a catalog stage; stages: {', '.join(CATALOG_STAGES)}", 2)
    if found is not None and found.language and search_language is None:
        overrides = [*overrides, *language_overrides(found.language)]
        settings, entries = checked(lambda: resolve_run(profile, overrides, env, depth))
    source, token = origin_option(origin, token_name)
    store = RunStore.from_settings(settings)
    try:
        request = RunRequest(
            query=query, sources=chosen, until=stop, depth=depth, kind=cast(RunKind, kind), structure=found
        )
        record = store.create(
            request,
            select_profile(profile, env),
            overrides,
            settings,
            attach or [],
            run_id,
            source,
            token,
            lock=True,
            use=entries,
            form=RunCreate.model_validate_json(form) if form else None,
        )
    except (ValidationError, RunStoreError) as error:
        raise fail(error, 2) from None
    start(store, settings, record, stop, as_json)


def fork(
    parent_id: Annotated[str, typer.Argument(help="The run to fork.")],
    from_: FromOption,
    until: UntilOption = None,
    profile: ProfileOption = None,
    use: UseOption = None,
    set_: SetOption = None,
    tone: ToneOption = None,
    tone_instructions: ToneInstructionsOption = None,
    words: WordsOption = None,
    language: LanguageOption = None,
    citation_marker: MarkerOption = None,
    reference_style: StyleOption = None,
    format_: FormatOption = None,
    context_tokens: ContextTokensOption = None,
    gap_context_tokens: GapContextTokensOption = None,
    model: ModelOption = None,
    context_window: ContextWindowOption = None,
    max_output: MaxOutputOption = None,
    plan_thinking: PlanThinkingOption = None,
    gap_thinking: GapThinkingOption = None,
    write_thinking: WriteThinkingOption = None,
    max_depth: MaxDepthOption = None,
    max_nodes: MaxNodesOption = None,
    pages_per_node: PagesPerNodeOption = None,
    run_id: RunIdOption = None,
    as_json: JsonOption = False,
    origin: OriginOption = "cli",
    token_name: TokenNameOption = None,
) -> None:
    """Copy a run up to --from and run the rest with the saved configuration plus new overrides."""
    first = stage_option(from_)
    assert first is not None
    stop = stage_option(until)
    source, token = origin_option(origin, token_name)
    flags = writing_overrides(
        tone=tone,
        tone_instructions=tone_instructions,
        words=words,
        language=language,
        citation_marker=citation_marker,
        reference_style=reference_style,
        format=format_,
    )
    limits: dict[str, int | str | None] = {
        "context_window": context_window,
        "max_output_tokens": max_output,
        "context_tokens": context_tokens,
        "gap_context_tokens": gap_context_tokens,
    }
    thinking = llm_overrides(model, limits, plan=plan_thinking, gap=gap_thinking, write=write_thinking)
    caps = catalog_limits(max_depth, max_nodes, pages_per_node)
    new = [*(set_ or []), *flags, *thinking, *limit_overrides(caps)]
    chosen = use_map(use)
    env = os.environ
    try:
        here = resolve_server(env)
    except ConfigError as error:
        raise fail(error, 2) from None
    store = RunStore.from_settings(here)
    try:
        parent = store.read_record(parent_id)
    except RunStoreError as error:
        raise fail(error, 2) from None
    if profile:
        overrides = [*without_use(parent.overrides), *new, *use_overrides(chosen)]
        settings, entries = checked(lambda: resolve_run(profile, overrides, env, parent.request.depth))
    else:
        dropped: list[str] = []

        def restored() -> Resolved:
            parent_use = parent.use or resolve_run(parent.profile, without_use(parent.overrides), env).use
            resolved, pruned = fork_settings(parent.settings, parent_use, chosen, new, env, parent.profile)
            dropped.extend(pruned)
            return resolved

        settings, entries = checked(restored)
        if dropped:
            typer.echo(f"warning: saved settings dropped: {', '.join(dropped)}", err=True)
    place = {"runs_dir": here.run.runs_dir, "cache_dir": here.run.cache_dir}
    settings = settings.model_copy(update={"run": settings.run.model_copy(update=place)})
    try:
        record = store.fork(
            parent_id,
            first,
            [*new, *use_overrides(chosen)],
            settings,
            profile=profile,
            use=entries,
            until=stop,
            run_id=run_id,
            origin=source,
            token_name=token,
            lock=True,
            limits=caps,
        )
    except RunStoreError as error:
        raise fail(error, 2) from None
    start(store, settings, record, stop, as_json)

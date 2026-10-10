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
from typing import Annotated, Literal, get_args

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
    DepthOption,
    FormatOption,
    FromOption,
    GapContextTokensOption,
    GapThinkingOption,
    JsonOption,
    LanguageOption,
    MarkerOption,
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
    WordsOption,
    WriteThinkingOption,
    fail,
    sources_option,
    stage_option,
)
from wosarcher.cli.progress import ProgressView
from wosarcher.config import RESEARCH_KEYS, ConfigError, Prices, Settings, resolve, restore_secrets, select_profile
from wosarcher.http import UsageLedger
from wosarcher.models import Context, Origin, Report, RunFailed, RunOutput, RunRecord, RunRequest, Stage
from wosarcher.runner import Runner
from wosarcher.runner.events import Listener
from wosarcher.store import RunStore, RunStoreError

Status = Literal["done", "failed", "cancelled"]
EXIT: dict[Status, int] = {"done": 0, "failed": 1, "cancelled": 130}
BLOCKS = ("search", "fetch", "prefilter", "score", "llm")

RunIdOption = Annotated[str | None, typer.Option("--run-id", help="Create the run under this ID.")]
OriginOption = Annotated[str, typer.Option("--origin", hidden=True)]
TokenNameOption = Annotated[str | None, typer.Option("--token-name", hidden=True)]


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


def llm_overrides(model: str | None, **reasoning: str | None) -> list[str]:
    """`--model` and the thinking flags as `llm.model` and `llm.reasoning.<step>` overrides."""
    found = [] if model is None else [f"llm.model={json.dumps(model)}"]
    return [*found, *(f"llm.reasoning.{step}={json.dumps(level)}" for step, level in reasoning.items() if level)]


def checked(make: Callable[[], Settings]) -> Settings:
    try:
        settings = make()
        building.check_providers(settings)
    except (ConfigError, ValueError) as error:
        raise fail(error, 2) from None
    return settings


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
            listeners.append(stack.enter_context(ProgressView(err, settings.research.rounds)))
        listeners.extend(diagnostics(view_shown=bool(listeners)))
        status = asyncio.run(execute(store, settings, record.run_id, until, listeners))
    output(store, record.run_id, status, as_json)
    raise typer.Exit(EXIT[status])


def output(store: RunStore, run_id: str, status: Status, as_json: bool) -> None:
    finished = store.finished_stages(run_id)
    error = next((e.data.error for e in reversed(store.read_events(run_id)) if isinstance(e, RunFailed)), None)
    context = store.read_artifact(run_id, "context.json", Context) if "select" in finished else None
    report = store.read_artifact(run_id, "report.json", Report) if "write" in finished else None
    if as_json:
        result = RunOutput(
            run_id=run_id, status=status, error=error if status == "failed" else None, context=context, report=report
        )
        typer.echo(result.model_dump_json(indent=2))
        return
    err = Console(stderr=True, highlight=False)
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
    plan_thinking: PlanThinkingOption = None,
    gap_thinking: GapThinkingOption = None,
    write_thinking: WriteThinkingOption = None,
    run_id: RunIdOption = None,
    as_json: JsonOption = False,
    origin: OriginOption = "cli",
    token_name: TokenNameOption = None,
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
        context_tokens=context_tokens,
        gap_context_tokens=gap_context_tokens,
        rounds=rounds,
        queries_per_round=queries_per_round,
    )
    domains = [*domain_overrides(allow_domain, block_domain), *language_overrides(search_language)]
    thinking = llm_overrides(model, plan=plan_thinking, gap=gap_thinking, write=write_thinking)
    overrides = [*(set_ or []), *flags, *research, *domains, *thinking]
    env = os.environ
    settings = checked(lambda: resolve(profile, overrides, env, depth))
    source, token = origin_option(origin, token_name)
    store = RunStore.from_settings(settings)
    try:
        request = RunRequest(query=query, sources=chosen, until=stop, depth=depth)
        record = store.create(
            request, select_profile(profile, env), overrides, settings, attach or [], run_id, source, token, lock=True
        )
    except (ValidationError, RunStoreError) as error:
        raise fail(error, 2) from None
    start(store, settings, record, stop, as_json)


def fork(
    parent_id: Annotated[str, typer.Argument(help="The run to fork.")],
    from_: FromOption,
    until: UntilOption = None,
    profile: ProfileOption = None,
    set_: SetOption = None,
    tone: ToneOption = None,
    tone_instructions: ToneInstructionsOption = None,
    words: WordsOption = None,
    language: LanguageOption = None,
    citation_marker: MarkerOption = None,
    reference_style: StyleOption = None,
    format_: FormatOption = None,
    gap_context_tokens: GapContextTokensOption = None,
    model: ModelOption = None,
    plan_thinking: PlanThinkingOption = None,
    gap_thinking: GapThinkingOption = None,
    write_thinking: WriteThinkingOption = None,
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
    research = research_overrides(gap_context_tokens=gap_context_tokens)
    thinking = llm_overrides(model, plan=plan_thinking, gap=gap_thinking, write=write_thinking)
    new = [*(set_ or []), *flags, *research, *thinking]
    env = os.environ
    here = checked(lambda: resolve(profile, set_ or [], env))
    store = RunStore.from_settings(here)
    try:
        parent = store.read_record(parent_id)
    except RunStoreError as error:
        raise fail(error, 2) from None
    if profile:
        settings = checked(lambda: resolve(profile, [*parent.overrides, *new], env, parent.request.depth))
    else:
        dropped: list[str] = []

        def restored() -> Settings:
            settings, pruned = restore_secrets(parent.settings, resolve(parent.profile, [], env), new)
            dropped.extend(pruned)
            return settings

        settings = checked(restored)
        if dropped:
            typer.echo(f"warning: saved settings dropped: {', '.join(dropped)}", err=True)
    place = {"runs_dir": here.run.runs_dir, "cache_dir": here.run.cache_dir}
    settings = settings.model_copy(update={"run": settings.run.model_copy(update=place)})
    try:
        record = store.fork(
            parent_id,
            first,
            new,
            settings,
            profile=profile,
            until=stop,
            run_id=run_id,
            origin=source,
            token_name=token,
            lock=True,
        )
    except RunStoreError as error:
        raise fail(error, 2) from None
    start(store, settings, record, stop, as_json)

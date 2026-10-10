"""`wosarcher run`, `wosarcher fork`, and `wosarcher runs`.

Exit status: 0 done, 1 failed, 130 cancelled, 2 invalid arguments or configuration, 75 no free run
slot with `--no-wait`.

A run takes a slot in the shared run queue (`store/slots.py`) after its
directory exists and before its first stage. The server starts its runs with
the slot already held (`--slot-fd`) and with their origin (`--origin`,
`--token-name`).
"""

import asyncio
import json
import logging
import os
import signal
import sys
from collections.abc import Callable
from contextlib import ExitStack, suppress
from typing import Annotated, Literal, get_args

import httpx
import typer
from pydantic import TypeAdapter, ValidationError
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

import wosarcher.build as building
from wosarcher.cli import ProfileOption, SetOption, fail
from wosarcher.cli.logs import stderr_listener
from wosarcher.cli.progress import ProgressView
from wosarcher.config import RESEARCH_KEYS, ConfigError, Prices, Settings, resolve, restore_secrets, select_profile
from wosarcher.http import UsageLedger
from wosarcher.models import (
    STAGES,
    Context,
    Effort,
    Origin,
    Report,
    RunCancelledData,
    RunFailed,
    RunOutput,
    RunRecord,
    RunRequest,
    RunSummary,
    SlotEntry,
    Sources,
    Stage,
    search_language,
)
from wosarcher.runner import Runner
from wosarcher.runner.events import Listener
from wosarcher.store import RunStore, RunStoreError, new_run_id
from wosarcher.store.slots import Held

Status = Literal["done", "failed", "cancelled"]
EXIT: dict[Status, int] = {"done": 0, "failed": 1, "cancelled": 130}
NO_SLOT = 75
"""`EX_TEMPFAIL`: try again later."""
SLOT_POLL = 0.5
BLOCKS = ("search", "fetch", "prefilter", "score", "llm")

UntilOption = Annotated[str | None, typer.Option("--until", help=f"Stop after this stage: {', '.join(STAGES)}.")]
RunIdOption = Annotated[str | None, typer.Option("--run-id", help="Create the run under this ID.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document when the run ends.")]
ToneOption = Annotated[str | None, typer.Option("--tone", help="Writing tone.")]
ToneInstructionsOption = Annotated[str | None, typer.Option("--tone-instructions", help="Extra tone instructions.")]
WordsOption = Annotated[int | None, typer.Option("--words", help="Target report length in words.")]
LanguageOption = Annotated[str | None, typer.Option("--language", help="Report language.")]
MarkerOption = Annotated[str | None, typer.Option("--citation-marker", help="numeric, superscript, or author-year.")]
StyleOption = Annotated[str | None, typer.Option("--reference-style", help="APA, MLA, Chicago, or IEEE.")]
FORMATS = ("report", "answer")
NoWaitOption = Annotated[
    bool, typer.Option("--no-wait", help=f"Exit with {NO_SLOT} instead of waiting when no run slot is free.")
]
SlotFdOption = Annotated[int | None, typer.Option("--slot-fd", hidden=True)]
OriginOption = Annotated[str, typer.Option("--origin", hidden=True)]
TokenNameOption = Annotated[str | None, typer.Option("--token-name", hidden=True)]


def format_option(value: str | None) -> str | None:
    if value is None or value in FORMATS:
        return value
    raise typer.BadParameter(f"must be one of: {', '.join(FORMATS)}")


FormatOption = Annotated[
    str | None,
    typer.Option("--format", metavar="report|answer", callback=format_option, help="Write a report or an answer."),
]
DepthOption = Annotated[str | None, typer.Option("--depth", help="Depth preset; see `wosarcher depth list`.")]


def stage_option(value: str | None) -> Stage | None:
    if value is None:
        return None
    if value not in STAGES:
        raise fail(ValueError(f"unknown stage '{value}'; valid stages: {', '.join(STAGES)}"), 2)
    return value


def writing_overrides(**fields: str | int | None) -> list[str]:
    """Writing flags as `write.<field>=<value>`, appended after `--set` so they win."""
    return [f"write.{name}={json.dumps(value)}" for name, value in fields.items() if value is not None]


def token_budget(value: str | None) -> str | None:
    """A positive integer or `auto`, for the token budget flags."""
    if value is None or value == "auto" or (value.isdigit() and int(value) > 0):
        return value
    raise typer.BadParameter("must be a positive integer or 'auto'")


ContextTokensOption = Annotated[
    str | None,
    typer.Option("--context-tokens", metavar="N|auto", callback=token_budget, help="Context token cap."),
]
GapContextTokensOption = Annotated[
    str | None,
    typer.Option(
        "--gap-context-tokens", metavar="N|auto", callback=token_budget, help="Gap step context token budget."
    ),
]


def research_overrides(**fields: int | str | None) -> list[str]:
    """Research flags as `--set` on their keys (`RESEARCH_KEYS`), appended after `--set` so they win."""
    return [f"{RESEARCH_KEYS[name]}={value}" for name, value in fields.items() if value is not None]


def domain_overrides(allow: list[str] | None, block: list[str] | None) -> list[str]:
    """Domain flags as JSON-list overrides of `search.allow_domains` and `search.block_domains`."""
    lists = {"search.allow_domains": allow, "search.block_domains": block}
    return [f"{key}={json.dumps(value)}" for key, value in lists.items() if value]


def language_option(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return search_language(value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None


SearchLanguageOption = Annotated[
    str | None,
    typer.Option(
        "--search-language", metavar="CODE", callback=language_option, help="Search language: all, auto, or a code."
    ),
]


def language_overrides(language: str | None) -> list[str]:
    """`--search-language` as a quoted `search.language` override."""
    return [] if language is None else [f"search.language={json.dumps(language)}"]


def effort_option(value: str | None) -> str | None:
    if value is None or value in get_args(Effort):
        return value
    raise typer.BadParameter(f"must be one of: {', '.join(get_args(Effort))}")


def thinking(step: str) -> object:
    return typer.Option(
        f"--{step}-thinking",
        metavar="LEVEL",
        callback=effort_option,
        help=f"Thinking for the {step} step: {', '.join(get_args(Effort))}.",
    )


ModelOption = Annotated[str | None, typer.Option("--model", help="Chat model for this run (llm.model).")]
PlanThinkingOption = Annotated[str | None, thinking("plan")]
GapThinkingOption = Annotated[str | None, thinking("gap")]
WriteThinkingOption = Annotated[str | None, thinking("write")]


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


async def watch_cancel(store: RunStore, run_id: str, task: asyncio.Task[Status]) -> None:
    """Cancel the run when another process asks for it (the server cannot signal this process)."""
    while True:
        await asyncio.sleep(SLOT_POLL)
        if store.slots.cancel_requested(run_id):
            task.cancel()
            return


async def execute(
    store: RunStore, settings: Settings, run_id: str, until: Stage | None, listeners: list[Listener]
) -> Status:
    """Run in a task that SIGTERM, SIGINT, and a cancel request cancel; return the run's status."""
    async with httpx.AsyncClient() as http:
        ledger = ledger_for(settings)
        runner = Runner(store, settings, building.build(settings, http, ledger), ledger, listeners)
        task = asyncio.create_task(runner.run(run_id, until))
        watcher = asyncio.create_task(watch_cancel(store, run_id, task))
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, task.cancel)
        try:
            return await task
        except asyncio.CancelledError:
            return "cancelled"
        finally:
            watcher.cancel()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)


async def wait_for_slot(store: RunStore, entry: SlotEntry, notify: Callable[[str], None]) -> Held | None:
    """Hold a queue place until a slot is granted; None when SIGINT, SIGTERM, or a cancel request ends the wait."""
    ticket = store.slots.ticket(entry)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        position: int | None = None
        while (held := store.slots.grant(ticket)) is None:
            if stop.is_set() or store.slots.cancel_requested(entry.run_id):
                ticket.close()
                return None
            now = store.slots.position(entry.run_id)
            if now is not None and now != position:
                position = now
                notify(f"waiting for a free run slot (position {position})")
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), SLOT_POLL)
        notify("")
        return held
    except BaseException:
        ticket.close()
        raise
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


async def wait_and_execute(
    store: RunStore,
    settings: Settings,
    record: RunRecord,
    until: Stage | None,
    held: Held | None,
    view: ProgressView | None,
    listeners: list[Listener],
) -> Status:
    def notify(text: str) -> None:
        if view is not None:
            view.show_notice(text)
        elif text:
            typer.echo(text, err=True)

    if held is None:
        entry = SlotEntry(run_id=record.run_id, origin=record.origin, token_name=record.token_name)
        held = await wait_for_slot(store, entry, notify)
    if held is None:
        store.append_event(record.run_id, "run.cancelled", None, RunCancelledData(stage=None))
        return "cancelled"
    try:
        return await execute(store, settings, record.run_id, until, listeners)
    finally:
        held.close()


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


def take_slot(
    store: RunStore, run_id: str | None, no_wait: bool, slot_fd: int | None
) -> tuple[str | None, Held | None]:
    """The run ID and the slot to run in: inherited from the server, taken at once (`--no-wait`), or None to wait."""
    if slot_fd is not None:
        assert run_id is not None
        return run_id, Held.inherit(store.slots, run_id, slot_fd)
    if not no_wait:
        return run_id, None
    run_id = run_id or new_run_id()
    held = store.slots.try_take(SlotEntry(run_id=run_id, origin="cli"))
    if held is None:
        state = store.slots.state()
        raise fail(RuntimeError(f"no free run slot ({len(state.held)} of {state.limit} in use)"), NO_SLOT)
    return run_id, held


def origin_option(origin: str, token_name: str | None) -> tuple[Origin, str | None]:
    if origin not in get_args(Origin):
        raise fail(ValueError(f"--origin must be one of: {', '.join(get_args(Origin))}"), 2)
    return origin, token_name if origin == "api" else None  # pyright: ignore[reportReturnType]


def start(
    store: RunStore, settings: Settings, record: RunRecord, until: Stage | None, as_json: bool, held: Held | None
) -> None:
    err = Console(stderr=True)
    with ExitStack() as stack:
        listeners: list[Listener] = []
        view = None
        if err.is_terminal and not as_json:
            view = stack.enter_context(ProgressView(err, settings.research.rounds))
            listeners.append(view)
        listeners.extend(diagnostics(view_shown=bool(listeners)))
        status = asyncio.run(wait_and_execute(store, settings, record, until, held, view, listeners))
    output(store, record.run_id, status, as_json)
    raise typer.Exit(EXIT[status])


def output(store: RunStore, run_id: str, status: Status, as_json: bool) -> None:
    finished = store.finished_stages(run_id)
    error = next((e.data.error for e in reversed(store.read_events(run_id)) if isinstance(e, RunFailed)), None)
    context = store.read_artifact(run_id, "context.json", Context) if "select" in finished else None
    report = store.read_artifact(run_id, "report.json", Report) if "write" in finished else None
    if as_json:
        result = RunOutput(
            run_id=run_id,
            status=status,
            error=error if status == "failed" else None,
            run_dir=str(store.run_dir(run_id)),
            context=context,
            report=report,
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
    attach: Annotated[list[str] | None, typer.Option("--attach", help="File, directory, or glob to attach.")] = None,
    sources: Annotated[str, typer.Option("--sources", help="files, web, or both.")] = "both",
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
    sub_queries: Annotated[int | None, typer.Option("--sub-queries", min=0, help="Sub-queries to plan.")] = None,
    results_per_query: Annotated[
        int | None, typer.Option("--results-per-query", min=1, help="Search results per query.")
    ] = None,
    max_pages: Annotated[int | None, typer.Option("--max-pages", min=1, help="Pages to fetch at most.")] = None,
    passages_per_query: Annotated[
        int | None, typer.Option("--passages-per-query", min=1, help="Passages kept per query.")
    ] = None,
    context_tokens: ContextTokensOption = None,
    gap_context_tokens: GapContextTokensOption = None,
    rounds: Annotated[int | None, typer.Option("--rounds", min=1, max=8, help="Research rounds.")] = None,
    queries_per_round: Annotated[
        int | None, typer.Option("--queries-per-round", min=1, help="Follow-up queries per round at most.")
    ] = None,
    search_language: SearchLanguageOption = None,
    allow_domain: Annotated[
        list[str] | None,
        typer.Option("--allow-domain", metavar="DOMAIN", help="Only use search results from this domain (repeatable)."),
    ] = None,
    block_domain: Annotated[
        list[str] | None,
        typer.Option("--block-domain", metavar="DOMAIN", help="Drop search results from this domain (repeatable)."),
    ] = None,
    model: ModelOption = None,
    plan_thinking: PlanThinkingOption = None,
    gap_thinking: GapThinkingOption = None,
    write_thinking: WriteThinkingOption = None,
    run_id: RunIdOption = None,
    as_json: JsonOption = False,
    no_wait: NoWaitOption = False,
    slot_fd: SlotFdOption = None,
    origin: OriginOption = "cli",
    token_name: TokenNameOption = None,
) -> None:
    """Research QUERY and write a report (or stop early with --until)."""
    stop = stage_option(until)
    if sources not in get_args(Sources):
        raise fail(ValueError(f"--sources must be one of: {', '.join(get_args(Sources))}"), 2)
    if sources == "files" and not attach:
        raise fail(ValueError("--sources files needs --attach"), 2)
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
        request = RunRequest(query=query, sources=sources, until=stop, depth=depth)  # pyright: ignore[reportArgumentType]
    except ValidationError as error:
        raise fail(error, 2) from None
    run_id, held = take_slot(store, run_id, no_wait, slot_fd)
    try:
        record = store.create(
            request, select_profile(profile, env), overrides, settings, attach or [], run_id, source, token
        )
    except RunStoreError as error:
        if held is not None:
            held.close()
        raise fail(error, 2) from None
    start(store, settings, record, stop, as_json, held)


def fork(
    parent_id: Annotated[str, typer.Argument(help="The run to fork.")],
    from_: Annotated[str, typer.Option("--from", help=f"First stage to run again: {', '.join(STAGES)}.")],
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
    no_wait: NoWaitOption = False,
    slot_fd: SlotFdOption = None,
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
    run_id, held = take_slot(store, run_id, no_wait, slot_fd)
    try:
        record = store.fork(
            parent_id, first, new, settings, profile=profile, until=stop, run_id=run_id, origin=source, token_name=token
        )
    except RunStoreError as error:
        if held is not None:
            held.close()
        raise fail(error, 2) from None
    start(store, settings, record, stop, as_json, held)


def runs(
    limit: Annotated[int, typer.Option("--limit", help="How many runs to list.")] = 20,
    profile: ProfileOption = None,
    set_: SetOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the list as a JSON array.")] = False,
) -> None:
    """List runs, newest first."""
    settings = checked(lambda: resolve(profile, set_ or [], os.environ))
    found = RunStore.from_settings(settings).list_runs(limit)
    if as_json:
        typer.echo(TypeAdapter(list[RunSummary]).dump_json(found, indent=2).decode())
        return
    table = Table("run", "created", "status", "origin", "version", "parent", "query")
    for item in found:
        created = f"{item.created:%Y-%m-%d %H:%M}"
        origin = f"api · {item.token_name}" if item.origin == "api" and item.token_name else item.origin
        row = (item.run_id, created, item.status, origin, str(item.version), item.parent_run_id or "", item.query)
        table.add_row(*row)
    Console(highlight=False).print(table)

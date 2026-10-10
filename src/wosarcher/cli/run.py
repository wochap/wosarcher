"""`wosarcher run`, `fork`, `runs`, and `cancel`, through the daemon's API.

A run is created with `POST /api/runs` (attachments uploaded) or
`POST /api/runs/{id}/fork`, then followed on its event socket from `since=0`
until a terminal event. SIGINT and SIGTERM send `POST /api/runs/{id}/cancel`
and keep reading until the run ends.

Exit status: 0 done, 1 failed, 130 cancelled, 2 invalid arguments or a request
the server rejects (and a run whose configuration the engine rejects before
its first stage), 69 no daemon.
"""

import asyncio
import logging
import os
import signal
import sys
from contextlib import ExitStack
from typing import Annotated, Literal

import typer
from pydantic import TypeAdapter, ValidationError
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from wosarcher.attachments import expand
from wosarcher.cli.api import Api, api, detail
from wosarcher.cli.logs import TERMINAL, Listener, stderr_listener
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
from wosarcher.models import (
    Context,
    DomainPatch,
    Event,
    ForkCreate,
    LLMPatch,
    ReasoningPatch,
    Report,
    ResearchPatch,
    RunCreate,
    RunCreated,
    RunFailed,
    RunOutput,
    RunQueued,
    RunStarted,
    RunSummary,
    StageDone,
    WritingPatch,
)

Status = Literal["done", "failed", "cancelled"]
EXIT: dict[Status, int] = {"done": 0, "failed": 1, "cancelled": 130}
STATUS: dict[str, Status] = {"run.done": "done", "run.failed": "failed", "run.cancelled": "cancelled"}
RECONNECT_SECONDS = 0.5


def writing_patch(**fields: str | int | None) -> WritingPatch:
    return WritingPatch.model_validate({name: value for name, value in fields.items() if value is not None})


def llm_patch(model: str | None, plan: str | None, gap: str | None, write: str | None) -> LLMPatch:
    reasoning = ReasoningPatch.model_validate({"plan": plan, "gap": gap, "write": write})
    return LLMPatch(model=model, reasoning=reasoning)


def uploads(paths: list[str]) -> list[tuple[str, tuple[str, bytes]]]:
    """Every file `--attach` names, as multipart `attachments` parts."""
    files: list[tuple[str, tuple[str, bytes]]] = []
    for path in paths:
        found = expand(path)
        if not found:
            raise fail(f"--attach {path}: no file matches", 2)
        files.extend(("attachments", (file.name, file.read_bytes())) for file in found)
    return files


class Follower:
    """Feeds a run's events to the progress view or the diagnostic lines, and remembers how it ended."""

    def __init__(self, listeners: list[Listener], view: ProgressView | None) -> None:
        self.listeners = listeners
        self.view = view
        self.position: int | None = None
        self.started = False
        self.finished: set[str] = set()
        self.terminal: Event | None = None
        self.last = 0

    def notify(self, text: str) -> None:
        if self.view is not None:
            self.view.show_notice(text)
        elif text:
            typer.echo(text, err=True)

    def __call__(self, event: Event) -> None:
        if isinstance(event, RunQueued):
            if event.data.position != self.position:
                self.position = event.data.position
                self.notify(f"waiting for a free run slot (position {self.position})")
            return
        if event.type in ("report.delta", "report.snapshot"):
            return
        if self.position is not None:
            self.position = None
            self.notify("")
        self.last = max(self.last, event.seq)
        self.started = self.started or isinstance(event, RunStarted)
        if isinstance(event, StageDone) and event.stage is not None:
            self.finished.add(event.stage)
        if event.type in TERMINAL:
            self.terminal = event
        for listener in self.listeners:
            listener(event)


async def follow(client: Api, run_id: str, follower: Follower) -> None:
    """Read the run's events until a terminal one; cancel the run on SIGINT or SIGTERM."""
    loop = asyncio.get_running_loop()
    cancelling: list[asyncio.Future[object]] = []

    def cancel() -> None:
        if not cancelling:
            cancelling.append(loop.run_in_executor(None, client.request, "POST", f"/api/runs/{run_id}/cancel"))

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, cancel)
    try:
        while follower.terminal is None:
            async for event in client.events(run_id, follower.last):
                follower(event)
                if follower.terminal is not None:
                    break
            if follower.terminal is None:
                await asyncio.sleep(RECONNECT_SECONDS)
        for future in cancelling:
            await future
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


def diagnostics(view_shown: bool) -> list[Listener]:
    """One line per run and stage event on standard error when no progress view is shown."""
    if view_shown:
        return []
    logger = logging.getLogger("wosarcher.client")
    logger.handlers.clear()
    logger.propagate = False
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return [stderr_listener(logger)]


def artifact[T](client: Api, run_id: str, name: str, model: type[T]) -> T | None:
    response = client.request("GET", f"/api/runs/{run_id}/artifacts/{name}")
    if not response.is_success:
        return None
    return TypeAdapter(model).validate_json(response.content)


def watch(client: Api, created: RunCreated, rounds: int, as_json: bool, early_exit: int) -> None:
    """Follow the run, print its output, and exit with its status."""
    err = Console(stderr=True)
    with ExitStack() as stack:
        listeners: list[Listener] = []
        view = None
        if err.is_terminal and not as_json:
            view = stack.enter_context(ProgressView(err, rounds))
            listeners.append(view)
        listeners.extend(diagnostics(view_shown=view is not None))
        follower = Follower(listeners, view)
        asyncio.run(follow(client, created.run_id, follower))
    assert follower.terminal is not None
    status = STATUS[follower.terminal.type]
    output(client, created.run_id, status, follower, as_json)
    rejected = status == "failed" and not follower.started
    raise typer.Exit(early_exit if rejected else EXIT[status])


def output(client: Api, run_id: str, status: Status, follower: Follower, as_json: bool) -> None:
    event = follower.terminal
    error = event.data.error if isinstance(event, RunFailed) else None
    context = artifact(client, run_id, "context.json", Context) if "select" in follower.finished else None
    report = artifact(client, run_id, "report.json", Report) if "write" in follower.finished else None
    if as_json:
        result = RunOutput(run_id=run_id, status=status, error=error, context=context, report=report)
        typer.echo(result.model_dump_json(indent=2))
        return
    err = Console(stderr=True, highlight=False)
    if status != "done":
        err.print(f"run {run_id} {status}" + (f": {error}" if error else ""), markup=False)
    if report is not None:
        text = client.ok("GET", f"/api/runs/{run_id}/artifacts/report.md").text
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
    err.print(f"run: {run_id}", markup=False)


def created(client: Api, path: str, **options: object) -> RunCreated:
    response = client.request("POST", path, **options)
    if response.status_code != 201:
        raise fail(detail(response), 2 if response.status_code < 500 else 1)
    return RunCreated.model_validate_json(response.content)


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
    as_json: JsonOption = False,
) -> None:
    """Research QUERY on the daemon and print the report (or stop early with --until)."""
    stop = stage_option(until)
    chosen = sources_option(sources, attach)
    budgets = {"context_tokens": context_tokens, "gap_context_tokens": gap_context_tokens}
    try:
        request = RunCreate(
            query=query,
            sources=chosen,
            until=stop,
            profile=profile,
            depth=depth,
            research=ResearchPatch.model_validate(
                {
                    "sub_queries": sub_queries,
                    "results_per_query": results_per_query,
                    "max_pages": max_pages,
                    "passages_per_query": passages_per_query,
                    "rounds": rounds,
                    "queries_per_round": queries_per_round,
                    **{name: int(value) if value and value.isdigit() else value for name, value in budgets.items()},
                }
            ),
            writing=writing_patch(
                tone=tone,
                tone_instructions=tone_instructions,
                words=words,
                language=language,
                citation_marker=citation_marker,
                reference_style=reference_style,
                format=format_,
            ),
            domains=DomainPatch(allow=allow_domain or None, block=block_domain or None),
            llm=llm_patch(model, plan_thinking, gap_thinking, write_thinking),
            search_language=search_language,
            set=set_ or [],
        )
    except ValidationError as error:
        raise fail(error, 2) from None
    files = uploads(attach or [])
    client = api(os.environ)
    body = [("request", (None, request.model_dump_json().encode())), *files]
    run = created(client, "/api/runs", files=body)
    watch(client, run, rounds or 1, as_json, early_exit=2)


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
    as_json: JsonOption = False,
) -> None:
    """Copy a run up to --from and run the rest with the saved configuration plus new overrides."""
    first = stage_option(from_)
    assert first is not None
    stop = stage_option(until)
    budget = [] if gap_context_tokens is None else [f"research.gap_context_tokens={gap_context_tokens}"]
    try:
        request = ForkCreate(
            from_stage=first,
            until=stop,
            writing=writing_patch(
                tone=tone,
                tone_instructions=tone_instructions,
                words=words,
                language=language,
                citation_marker=citation_marker,
                reference_style=reference_style,
                format=format_,
            ),
            llm=llm_patch(model, plan_thinking, gap_thinking, write_thinking),
            set=[*(set_ or []), *budget],
            profile=profile,
        )
    except ValidationError as error:
        raise fail(error, 2) from None
    client = api(os.environ)
    parent = client.request("GET", f"/api/runs/{parent_id}")
    rounds = parent.json().get("rounds_planned", 1) if parent.is_success else 1
    body = request.model_dump(mode="json", by_alias=True, exclude_none=True)
    run = created(client, f"/api/runs/{parent_id}/fork", json=body)
    watch(client, run, rounds, as_json, early_exit=1)


def origin_label(item: RunSummary) -> str:
    return f"api · {item.token_name}" if item.origin == "api" and item.token_name else item.origin


def runs(
    limit: Annotated[int, typer.Option("--limit", help="How many runs to list.")] = 20,
    as_json: Annotated[bool, typer.Option("--json", help="Print the list as a JSON array.")] = False,
) -> None:
    """List runs, newest first."""
    found = TypeAdapter(list[RunSummary]).validate_python(api(os.environ).get("/api/runs"))[:limit]
    if as_json:
        typer.echo(TypeAdapter(list[RunSummary]).dump_json(found, indent=2).decode())
        return
    table = Table("run", "created", "status", "origin", "version", "parent", "query")
    for item in found:
        created_at = f"{item.created:%Y-%m-%d %H:%M}"
        row = (item.run_id, created_at, item.status, origin_label(item), str(item.version), item.parent_run_id or "")
        table.add_row(*row, item.query)
    Console(highlight=False).print(table)


def cancel(run_id: Annotated[str, typer.Argument(help="The run to cancel.")]) -> None:
    """Cancel a queued or running run."""
    result = api(os.environ).ok("POST", f"/api/runs/{run_id}/cancel").json()
    typer.echo(f"run {run_id}: {result['result']}")

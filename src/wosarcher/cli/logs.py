"""`wosarcher logs`, and the one-line event format it shares with the run process's standard error."""

import asyncio
import logging
import os
from collections.abc import Callable
from typing import Annotated

import typer

from wosarcher.cli.api import Api, api
from wosarcher.cli.options import fail
from wosarcher.models import (
    Event,
    HitFound,
    PageFailed,
    PageFetched,
    PassagesScored,
    PlanReady,
    ResourceReleased,
    ResourceWaiting,
    RunCancelled,
    RunDone,
    RunFailed,
    RunStarted,
    StageDone,
    StageFailed,
    StageProgress,
    StageStarted,
    parse_event,
)

Listener = Callable[[Event], None]
SUMMARY_MAX_CHARS = 160
LIVE_ONLY = {"report.delta", "report.snapshot", "run.queued"}
TERMINAL = {"run.done", "run.failed", "run.cancelled"}
LOGGED = {
    "run.started",
    "run.done",
    "run.failed",
    "run.cancelled",
    "stage.started",
    "stage.done",
    "stage.failed",
    "resource.waiting",
    "resource.released",
}
WARNING_TYPES = {"run.failed", "stage.failed"}


def stage_done(event: StageDone) -> str:
    done = event.data
    parts = [f"count={done.count} {done.seconds:.1f}s provider={done.provider or '-'}"]
    if done.skipped:
        parts.append("skipped")
    if done.copied_from:
        parts.append(f"copied from {done.copied_from}")
    if done.warnings:
        parts.append(f"{len(done.warnings)} warnings")
    return " ".join(parts)


def summary(event: Event) -> str:
    match event:
        case RunStarted():
            return event.data.query
        case StageStarted():
            return f"provider={event.data.provider} device={event.data.device or '-'}"
        case StageDone():
            return stage_done(event)
        case StageFailed():
            return f"{event.data.error} -> next={event.data.next or 'none'}"
        case RunFailed():
            return f"{event.data.stage or '-'}: {event.data.error}"
        case RunCancelled():
            return event.data.stage or "-"
        case RunDone():
            return f"until={event.data.until or 'write'}"
        case PageFetched():
            return f"{event.data.url} {event.data.chars} chars" + (" cached" if event.data.cached else "")
        case PageFailed():
            return f"{event.data.url}: {event.data.reason}"
        case HitFound():
            return event.data.url
        case PlanReady():
            return f"{len(event.data.queries)} sub-queries"
        case PassagesScored():
            data = event.data
            return f"{data.query_id} kept {data.kept}/{data.scored} by {data.scorer}"
        case ResourceWaiting() | ResourceReleased():
            return f"{event.data.device} {event.data.released_stage}"
        case StageProgress():
            return f"{event.data.done}/{event.data.total} failed {event.data.failed}"
        case _:
            return event.data.model_dump_json()


def event_line(event: Event) -> str:
    """`<HH:MM:SS> <stage or -> <type> <summary>`, local time, the summary on one line and cut to 160 characters."""
    text = " ".join(summary(event).splitlines())
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[: SUMMARY_MAX_CHARS - 1] + "…"
    return f"{event.ts.astimezone():%H:%M:%S} {event.stage or '-'} {event.type} {text}"


def stderr_listener(logger: logging.Logger) -> Listener:
    """Run and stage events, and each `stage.done` warning, as log lines."""

    def listen(event: Event) -> None:
        if event.type in LOGGED:
            level = logging.WARNING if event.type in WARNING_TYPES else logging.INFO
            logger.log(level, "%s", event_line(event))
        if isinstance(event, StageDone):
            for warning in event.data.warnings:
                logger.warning("warning %s: %s", event.stage or "-", warning)

    return listen


def logs(
    run_id: Annotated[str, typer.Argument(help="The run to show.")],
    follow: Annotated[bool, typer.Option("--follow", help="Keep printing new events until the run ends.")] = False,
) -> None:
    """Print a run's logged events, one line each."""
    client = api(os.environ)
    if client.request("GET", f"/api/runs/{run_id}").status_code == 404:
        raise fail(f"no run {run_id}", 2)
    if follow:
        asyncio.run(follow_events(client, run_id))
        return
    response = client.request("GET", f"/api/runs/{run_id}/artifacts/events.jsonl")
    if not response.is_success:
        return
    for line in response.text.splitlines():
        try:
            typer.echo(event_line(parse_event(line)))
        except ValueError:
            continue


async def follow_events(client: Api, run_id: str) -> None:
    async for event in client.events(run_id):
        if event.type not in LIVE_ONLY:
            typer.echo(event_line(event))
        if event.type in TERMINAL:
            return

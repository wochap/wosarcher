"""`wosarcher logs`, and the one-line event format it shares with the run process's standard error."""

import logging
import os
import time
from typing import Annotated

import typer

from wosarcher.cli import ProfileOption, SetOption, fail
from wosarcher.config import ConfigError, resolve
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
)
from wosarcher.runner.events import Listener
from wosarcher.store import RunStore

SUMMARY_MAX_CHARS = 160
FOLLOW_SECONDS = 0.5
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
    profile: ProfileOption = None,
    set_: SetOption = None,
) -> None:
    """Print a run's logged events, one line each."""
    try:
        settings = resolve(profile, set_ or [], os.environ)
    except ConfigError as error:
        raise fail(error, 2) from None
    store = RunStore.from_settings(settings)
    if not (store.run_dir(run_id) / "request.json").is_file():
        raise fail(ValueError(f"no run {run_id} in {store.runs_dir}"), 2)
    last = 0
    while True:
        for event in store.read_events(run_id, since=last):
            typer.echo(event_line(event))
            last = event.seq
            if event.type in TERMINAL:
                return
        if not follow:
            return
        time.sleep(FOLLOW_SECONDS)

"""Pauses: a run asks questions through its run directory and waits for the answers.

The run writes `input/<id>.json` and emits `input.needed`, then checks once per second for
`input/<id>.answer.json` (written by the server or the CLI) and the presence file `input/<id>.hold`. When the
deadline passes it answers itself with the recommended options. Nothing here calls a model.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wosarcher.models import (
    Answer,
    InputAnsweredData,
    InputNeededData,
    Pause,
    PauseKind,
    Question,
    QuestionsAnswered,
    Stage,
    recommended_answers,
)
from wosarcher.runner.devices import GPU_BLOCK
from wosarcher.runner.events import EventLog
from wosarcher.store import RunStore, deadline_of

if TYPE_CHECKING:
    from wosarcher.runner import Runner

POLL_SECONDS = 1.0
TOLERANCE = 0.001
"""Seconds; a timestamp survives a datetime round trip only to the microsecond."""


@dataclass
class Waiter:
    """The clock and the sleep a pause uses; tests replace both."""

    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    now: Callable[[], float] = time.time


@dataclass(frozen=True)
class Reply:
    answers: list[Answer]
    answered_by: str
    asked: bool
    """False when no pause happened (a fork or rerun): the recommended answers."""


@dataclass
class Asker:
    """What a stage needs to pause: the store, the log, the run's question settings, and the waiter."""

    store: RunStore
    log: EventLog
    run_id: str
    enabled: bool
    """False for forks and reruns, which never pause."""
    timeout: int
    max_wait: int
    waiter: Waiter = field(default_factory=Waiter)
    runner: "Runner | None" = None

    def next_id(self) -> int:
        return len(self.store.read_pauses(self.run_id)) + 1

    async def ask(
        self, stage: Stage, kind: PauseKind, questions: list[Question], *, after: int | None = None, context: str = ""
    ) -> Reply:
        """Pause with `questions` and return the answers; the recommended ones for a fork or rerun."""
        if not self.enabled:
            return Reply(recommended_answers(questions), "timeout", False)
        pause = Pause(
            id=self.next_id(),
            kind=kind,
            after=after,
            context=context,
            questions=questions,
            created=datetime.fromtimestamp(self.waiter.now(), UTC),
            timeout=self.timeout,
            max_wait=self.max_wait,
        )
        await self.release(stage)
        self.store.write_pause(self.run_id, pause)
        needed = InputNeededData(
            pause_id=pause.id,
            kind=kind,
            after=after,
            context=context,
            questions=questions,
            created=pause.created,
            timeout=pause.timeout,
            max_wait=pause.max_wait,
        )
        self.log.emit("input.needed", stage, needed)
        answered = await self.wait(pause)
        waited = round(self.waiter.now() - pause.created.timestamp(), 3)
        self.store.write_pause(
            self.run_id, pause.model_copy(update={"answers": answered.answers, "answered_by": answered.answered_by})
        )
        data = InputAnsweredData(
            pause_id=pause.id, answers=answered.answers, answered_by=answered.answered_by, seconds_waited=waited
        )
        self.log.emit("input.answered", stage, data)
        return Reply(answered.answers, answered.answered_by, True)

    async def wait(self, pause: Pause) -> QuestionsAnswered:
        """Poll for the answer file until it appears or the deadline passes; then answer with the recommendations."""
        while True:
            found = self.store.read_answer(self.run_id, pause.id)
            if found is not None:
                return found
            deadline = deadline_of(pause, self.store.hold_time(self.run_id, pause.id))
            if self.waiter.now() >= deadline.timestamp() - TOLERANCE:
                answered = QuestionsAnswered(answers=recommended_answers(pause.questions), answered_by="timeout")
                self.store.write_answer(self.run_id, pause.id, answered)
                return answered
            await self.waiter.sleep(POLL_SECONDS)

    async def release(self, stage: Stage) -> None:
        """A waiting run holds no device: release the stage's model first, as the exclusive policy does."""
        runner = self.runner
        if runner is None or runner.settings.run.gpu_policy != "exclusive" or stage not in GPU_BLOCK:
            return
        with suppress(Exception):
            await runner.release(stage)

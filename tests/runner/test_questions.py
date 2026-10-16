"""Pauses with fakes: the answer file, the timeout, presence, the clarify pause, and forks."""

import asyncio
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

from tests.runner.helpers import PLAN_REPLY, QUERY, adapters, new_run, settings
from wosarcher.adapters.fakes import FakeLLM
from wosarcher.config import QuestionsConfig, Settings
from wosarcher.http import UsageLedger
from wosarcher.models import (
    Answer,
    InputAnswered,
    InputNeeded,
    Plan,
    Question,
    QuestionOption,
    QuestionsAnswered,
    StageDone,
)
from wosarcher.ports import Adapters
from wosarcher.runner import Runner
from wosarcher.runner.events import EventLog
from wosarcher.runner.questions import Asker, Waiter
from wosarcher.store import RunStore

CLARIFY = json.dumps(
    {
        "questions": [
            {
                "text": "Include regional governments?",
                "kind": "confirm",
                "options": [{"label": "Yes", "recommended": True}, {"label": "No"}],
            },
            {
                "text": "Which sources?",
                "kind": "multi",
                "options": [{"label": "Official", "recommended": True}, {"label": "News"}],
                "allow_other": True,
            },
        ]
    }
)
REPLAN = '{"topic": "regional only", "queries": ["regional cost"], "parts": ["cost"]}'


class Clock:
    """A fake clock: every sleep advances it and may run a hook, so a pause can be answered at a chosen time."""

    def __init__(self, hook: Callable[["Clock"], None] | None = None) -> None:
        self.time = time.time()
        self.start = self.time
        self.hook = hook
        self.sleeps = 0

    def now(self) -> float:
        return self.time

    async def sleep(self, seconds: float) -> None:
        self.time += seconds
        self.sleeps += 1
        await asyncio.sleep(0)
        if self.hook is not None:
            self.hook(self)

    @property
    def waiter(self) -> Waiter:
        return Waiter(sleep=self.sleep, now=self.now)

    @property
    def elapsed(self) -> float:
        return self.time - self.start


def questions() -> list[Question]:
    options = [QuestionOption(id="a", label="Yes", recommended=True), QuestionOption(id="b", label="No")]
    return [Question(id="q1", text="Go on?", kind="confirm", options=options)]


def asker(tmp_path: Path, clock: Clock, *, timeout: int = 60, max_wait: int = 1800, enabled: bool = True) -> Asker:
    cfg = settings(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg)
    return Asker(store, EventLog(store, run_id), run_id, enabled, timeout, max_wait, clock.waiter)


def events(found: Asker) -> list[InputNeeded | InputAnswered]:
    return [e for e in found.store.read_events(found.run_id) if isinstance(e, InputNeeded | InputAnswered)]


async def test_answered_by_user(tmp_path: Path) -> None:
    def answer(clock: Clock) -> None:
        if clock.elapsed >= 20:
            found.store.write_answer(
                found.run_id,
                1,
                QuestionsAnswered(answers=[Answer(question_id="q1", option_ids=["b"])], answered_by="user"),
            )

    clock = Clock(answer)
    found = asker(tmp_path, clock)
    reply = await found.ask("plan", "clarify", questions(), context="I read the brief as: x")
    assert [a.option_ids for a in reply.answers] == [["b"]]
    needed, answered = events(found)
    assert isinstance(needed, InputNeeded)
    assert isinstance(answered, InputAnswered)
    assert (needed.stage, needed.data.pause_id, needed.data.timeout) == ("plan", 1, 60)
    assert (answered.data.answered_by, round(answered.data.seconds_waited)) == ("user", 20)
    pause = found.store.read_pause(found.run_id, 1)
    assert pause is not None
    assert pause.answered_by == "user"


async def test_timeout_while_idle(tmp_path: Path) -> None:
    clock = Clock()
    found = asker(tmp_path, clock)
    reply = await found.ask("gap", "round", questions(), after=1)
    assert reply.answers == [Answer(question_id="q1", option_ids=["a"])]
    answered = events(found)[1]
    assert isinstance(answered, InputAnswered)
    assert answered.data.answered_by == "timeout"
    assert 60 <= clock.elapsed < 62
    assert found.store.read_answer(found.run_id, 1) is not None


async def test_presence_moves_the_deadline(tmp_path: Path) -> None:
    def touch(clock: Clock) -> None:
        hold = found.store.input_dir(found.run_id) / "1.hold"
        if clock.elapsed < 30 and not hold.exists():
            hold.touch()
            os.utime(hold, (clock.now() + 30, clock.now() + 30))

    clock = Clock(touch)
    found = asker(tmp_path, clock)
    await found.ask("gap", "round", questions(), after=1)
    assert 90 <= clock.elapsed < 93


async def test_ceiling(tmp_path: Path) -> None:
    def present(clock: Clock) -> None:
        found.store.touch_hold(found.run_id, 1)
        os.utime(found.store.input_dir(found.run_id) / "1.hold", (clock.now(), clock.now()))

    clock = Clock(present)
    found = asker(tmp_path, clock, timeout=60, max_wait=120)
    await found.ask("gap", "round", questions(), after=1)
    assert 120 <= clock.elapsed < 122
    answered = events(found)[1]
    assert isinstance(answered, InputAnswered)
    assert answered.data.answered_by == "timeout"


async def test_zero_timeout_continues_at_once(tmp_path: Path) -> None:
    clock = Clock()
    found = asker(tmp_path, clock, timeout=0)
    await found.ask("gap", "round", questions(), after=1)
    assert clock.sleeps == 0


async def test_disabled_does_not_pause(tmp_path: Path) -> None:
    clock = Clock()
    found = asker(tmp_path, clock, enabled=False)
    reply = await found.ask("gap", "round", questions(), after=1)
    assert (reply.asked, events(found)) == (False, [])


def ask_settings(tmp_path: Path, clarify: bool = True) -> Settings:
    return settings(tmp_path, QuestionsConfig(clarify=clarify, rounds=False))


def planner_world(*replies: str) -> Adapters:
    return adapters(planner=FakeLLM([PLAN_REPLY, *replies]))


async def run_until_plan(cfg: Settings, run_id: str, fakes: Adapters, clock: Clock) -> str:
    store = RunStore.from_settings(cfg)
    return await Runner(store, cfg, fakes, UsageLedger({}), waiter=clock.waiter).run(run_id, "plan")


def answer_with(store: RunStore, run_id: str, option: str) -> Callable[[Clock], None]:
    def hook(clock: Clock) -> None:
        pause = store.read_pause(run_id, 1)
        if pause is not None and store.read_answer(run_id, 1) is None:
            answers = [Answer(question_id=q.id, option_ids=[option if q.id == "q1" else "a"]) for q in pause.questions]
            store.write_answer(run_id, 1, QuestionsAnswered(answers=answers, answered_by="user"))

    return hook


async def test_recommended_answers_keep_the_plan(tmp_path: Path) -> None:
    cfg = ask_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg)
    fakes = planner_world(CLARIFY)
    clock = Clock(answer_with(store, run_id, "a"))
    assert await run_until_plan(cfg, run_id, fakes, clock) == "done"
    assert isinstance(fakes.planner, FakeLLM)
    assert len(fakes.planner.calls) == 2
    record = store.read_record(run_id)
    assert [(c.question, c.answer) for c in record.clarifications] == [
        ("Include regional governments?", "Yes"),
        ("Which sources?", "Official"),
    ]
    assert record.request.query.startswith(QUERY + "\n\nClarifications:\n- Include regional governments? Yes")
    assert store.summary(record).query == QUERY
    assert store.read_artifact(run_id, "plan.json", Plan).queries[0].text == "battery recycling"


async def test_changed_answer_replans(tmp_path: Path) -> None:
    cfg = ask_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg)
    fakes = planner_world(CLARIFY, REPLAN)
    clock = Clock(answer_with(store, run_id, "b"))
    assert await run_until_plan(cfg, run_id, fakes, clock) == "done"
    assert isinstance(fakes.planner, FakeLLM)
    assert len(fakes.planner.calls) == 3
    assert "Clarifications:\n- Include regional governments? No" in fakes.planner.calls[2][0].content
    assert store.read_artifact(run_id, "plan.json", Plan).queries[0].text == "regional only"


async def test_no_question_no_pause(tmp_path: Path) -> None:
    cfg = ask_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg)
    assert await run_until_plan(cfg, run_id, planner_world('{"questions": []}'), Clock()) == "done"
    assert not [e for e in store.read_events(run_id) if isinstance(e, InputNeeded)]
    done = [e for e in store.read_events(run_id) if isinstance(e, StageDone) and e.stage == "plan"]
    assert done[0].data.warnings == []


async def test_clarify_off(tmp_path: Path) -> None:
    cfg = ask_settings(tmp_path, clarify=False)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg)
    fakes = planner_world(CLARIFY)
    assert await run_until_plan(cfg, run_id, fakes, Clock()) == "done"
    assert isinstance(fakes.planner, FakeLLM)
    assert len(fakes.planner.calls) == 1


async def test_clarify_call_failed(tmp_path: Path) -> None:
    cfg = ask_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg)
    assert await run_until_plan(cfg, run_id, planner_world("not json"), Clock()) == "done"
    done = [e for e in store.read_events(run_id) if isinstance(e, StageDone) and e.stage == "plan"]
    assert done[0].data.warnings[0].startswith("clarify failed:")
    assert not [e for e in store.read_events(run_id) if isinstance(e, InputNeeded)]


async def test_fork_does_not_ask(tmp_path: Path) -> None:
    cfg = ask_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_run(store, cfg)
    clock = Clock(answer_with(store, run_id, "a"))
    await Runner(store, cfg, planner_world(CLARIFY), UsageLedger({}), waiter=clock.waiter).run(run_id)
    parent = store.read_record(run_id)
    fork = store.fork(run_id, "write", [], cfg)
    assert fork.request.query == parent.request.query
    fakes = planner_world(CLARIFY)
    await Runner(store, cfg, fakes, UsageLedger({}), waiter=Clock().waiter).run(fork.run_id)
    assert not [e for e in store.read_events(fork.run_id) if isinstance(e, InputNeeded)]

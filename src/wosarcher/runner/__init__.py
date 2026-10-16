"""Run the stages of a run directory in order: one phase per stage, events, devices, timeouts, and costs.

`Runner.run(run_id)` executes every unfinished stage, so it starts new runs,
resumes, and continues forks the same way.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Literal

from wosarcher.config import Settings
from wosarcher.http import Usage, UsageLedger
from wosarcher.models import (
    CATALOG_STAGES,
    LOOP_STAGES,
    STAGES,
    Page,
    Plan,
    Query,
    Question,
    QuestionOption,
    ResearchDoneData,
    ResearchRecord,
    ResourceData,
    RoundDoneData,
    RoundRecord,
    RunCancelledData,
    RunCosts,
    RunDoneData,
    RunFailedData,
    RunRecord,
    RunStartedData,
    Sources,
    Stage,
    StageDoneData,
    StageStartedData,
    StopReason,
    UsageTotals,
)
from wosarcher.ports import Adapters
from wosarcher.runner import catalog, steps
from wosarcher.runner.caches import CachedFetcher
from wosarcher.runner.devices import GPU_BLOCK, gpu_device, needs_release, next_gpu_stage, stage_provider
from wosarcher.runner.events import EventLog, Listener
from wosarcher.runner.preflight import preflight
from wosarcher.runner.questions import Asker, Waiter
from wosarcher.stages import gap as gapping
from wosarcher.store import STAGE_ARTIFACTS, RunStore
from wosarcher.store.caches import PageCache

SKIPPED_BY: dict[Sources, set[Stage]] = {"both": set(), "web": {"load"}, "files": {"search", "fetch"}}
RunEnd = Literal["done", "failed"]
ROUND_STAGES: tuple[Stage, ...] = LOOP_STAGES[:-1]
"""The loop stages every round runs; `gap` follows all but the last."""
LOOP_ARTIFACTS = ("hits.jsonl", "pages.jsonl", "chunks.jsonl", "candidates.jsonl", "scores.jsonl")
END_NOTES: dict[StopReason, str] = {
    "no new sources": "Follow-up searches returned only pages fetched in earlier rounds.",
    "no follow-ups": "The gap step wrote no usable follow-up query.",
}
MAX_PAUSE_OPTIONS = 6
LETTERS = "abcdefghijklmnopqrstuvwxyz"


class StageError(Exception):
    def __init__(self, stage: Stage, error: str) -> None:
        super().__init__(f"{stage}: {error}")
        self.stage: Stage = stage
        self.error = error


def totals(usage: Usage) -> UsageTotals:
    return UsageTotals(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        requests=usage.requests,
        units=usage.units,
        cost=usage.cost,
    )


def plus(a: Usage, b: Usage, sign: int = 1) -> Usage:
    return Usage(
        requests=a.requests + sign * b.requests,
        input_tokens=a.input_tokens + sign * b.input_tokens,
        output_tokens=a.output_tokens + sign * b.output_tokens,
        units=a.units + sign * b.units,
        cost=a.cost + sign * b.cost,
    )


def empty_fails(stage: Stage, sources: Sources, files: int) -> bool:
    """Whether a stage with no output fails the run."""
    if stage == "load":
        return sources == "files"
    if stage in ("plan", "gap"):
        return False
    if stage == "search":
        return sources == "web"
    if stage == "fetch":
        return sources == "web" or (sources == "both" and files == 0)
    return True


@dataclass
class Runner:
    store: RunStore
    settings: Settings
    adapters: Adapters
    ledger: UsageLedger
    listeners: Sequence[Listener] = ()
    stage_usage: dict[str, Usage] = field(default_factory=dict[str, Usage])
    warnings: list[str] = field(default_factory=list[str])
    """Release errors, reported on the next `stage.done`."""
    current: Stage | None = None
    """The stage running now; a cancelled run reports it."""
    waiter: Waiter = field(default_factory=Waiter)
    """The clock and sleep of a pause; tests replace it."""

    async def run(self, run_id: str, until: Stage | None = None) -> RunEnd:
        """Run every unfinished stage up to `until`; return `done` or `failed`. Cancellation re-raises."""
        record = self.store.read_record(run_id)
        log = EventLog(self.store, run_id, self.listeners)
        cache = PageCache(self.store.cache_dir / "pages", self.settings.run.page_cache_ttl_hours)
        fetcher = CachedFetcher(self.adapters.fetcher, cache)
        is_catalog = record.kind == "catalog"
        context = catalog.CatalogContext if is_catalog else steps.StepContext
        ctx = context(self.store, record, self.settings, self.adapters, log, fetcher)
        questions = self.settings.questions
        ctx.asker = Asker(
            self.store,
            log,
            run_id,
            enabled=record.parent_run_id is None,
            timeout=questions.timeout,
            max_wait=questions.max_wait,
            waiter=self.waiter,
            runner=self,
        )
        order = CATALOG_STAGES if is_catalog else STAGES
        if until is not None and until not in order:
            log.emit("run.started", None, self.started(record, until))
            error = f"--until {until} is not a stage of a {record.kind} run; stages: {', '.join(order)}"
            log.emit("run.failed", None, RunFailedData(stage=None, error=error))
            return "failed"
        finished = self.store.finished_stages(run_id)
        last = order.index(until) if until else len(order) - 1
        todo: list[Stage] = [stage for stage in order[: last + 1] if stage not in finished]
        skipped = SKIPPED_BY[record.request.sources]
        runnable: list[Stage] = [stage for stage in todo if stage not in skipped]
        log.emit("run.started", None, self.started(record, until))
        self.current = None
        if not is_catalog and "search" in todo and "plan" not in todo:
            self.restart_loop(run_id)
        try:
            down = await preflight(self.settings, self.adapters.managed, runnable)
            if down:
                raise StageError(*down)
            if is_catalog and record.request.sources == "files":
                raise StageError(todo[0] if todo else "load", "a catalog run cannot use sources files")
            if isinstance(ctx, catalog.CatalogContext):
                await catalog.run_stages(self, ctx, todo, until)
                todo = []
            looped = False
            for stage in todo:
                self.current = stage
                if looped and stage in LOOP_STAGES:
                    continue
                if stage == "search" and ctx.planned_rounds() > 1:
                    looped = True
                    after: list[Stage] = [name for name in runnable if name not in LOOP_STAGES]
                    await self.research(ctx, until, after)
                    continue
                if stage in skipped or stage == "gap":
                    self.skip(ctx, stage)
                    continue
                await self.run_stage(ctx, stage)
                following: list[Stage] = [name for name in runnable[runnable.index(stage) + 1 :] if name != "gap"]
                await self.maybe_release(ctx, stage, following)
        except StageError as failure:
            self.write_costs(run_id)
            log.emit("run.failed", None, RunFailedData(stage=failure.stage, error=failure.error))
            return "failed"
        except asyncio.CancelledError:
            current = self.current
            if current is not None and self.settings.run.gpu_policy == "exclusive":
                with suppress(Exception):
                    await asyncio.shield(self.release(current))
            with suppress(Exception):
                self.write_costs(run_id)
            log.emit("run.cancelled", None, RunCancelledData(stage=current))
            raise
        self.write_costs(run_id)
        log.emit("run.done", None, RunDoneData(until=until, totals=totals(self.ledger.total())))
        return "done"

    def started(self, record: RunRecord, until: Stage | None) -> RunStartedData:
        return RunStartedData(
            query=record.request.query,
            kind=record.kind,
            profile=record.profile,
            parent_run_id=record.parent_run_id,
            version=record.version,
            until=until,
        )

    def restart_loop(self, run_id: str) -> None:
        """Before the loop runs again: the plan back to its round-1 queries, the loop's artifacts emptied."""
        path = self.store.run_dir(run_id) / "plan.json"
        if not path.is_file():
            return
        plan = self.store.read_artifact(run_id, "plan.json", Plan)
        first = [query for query in plan.queries if query.round == 1]
        self.store.write_artifact(run_id, "plan.json", plan.model_copy(update={"queries": first}))
        for name in LOOP_ARTIFACTS:
            self.store.write_text(run_id, name, "")
        (self.store.run_dir(run_id) / "research.json").unlink(missing_ok=True)

    async def research(self, ctx: steps.StepContext, until: Stage | None, after: list[Stage]) -> None:
        """Run search through score once per round, with a gap step between rounds, until a stop rule holds."""
        planned = ctx.planned_rounds()
        state = ctx.round
        rounds: list[RoundRecord] = []
        reason: StopReason | None = None
        gap_ran = False
        while reason is None:
            for stage in ROUND_STAGES:
                await self.run_stage(ctx, stage)
                if stage == until:
                    return
                await self.maybe_release(ctx, stage, self.cycle(stage, after))
            query_ids = [query.id for query in ctx.round_queries() if query.id != "q0"]
            data = RoundDoneData(
                round=state.number,
                query_ids=query_ids,
                new_pages=state.new_pages,
                known_pages=state.known_pages,
                kept=state.kept,
            )
            ctx.log.emit("round.done", "score", data)
            rounds.append(RoundRecord(**data.model_dump()))
            reason = self.stop_before_gap(state, planned)
            if reason is not None:
                break
            await self.run_stage(ctx, "gap")
            gap_ran = True
            if until == "gap":
                return
            await self.maybe_release(ctx, "gap", self.cycle("gap", after))
            if state.gap_error is not None or state.gap is None:
                reason = "gap step failed"
            else:
                rounds[-1] = rounds[-1].model_copy(
                    update={"note": state.gap.note, "uncovered": state.gap.uncovered, "missing": state.gap.missing}
                )
                if not state.gap.queries:
                    reason = "no follow-ups"
                else:
                    reason, rounds[-1] = await self.round_pause(ctx, rounds[-1])
            if reason is None:
                state.next()
                ctx.log.round = state.number
        note = self.end_note(reason, state.number, dropped=bool(rounds[-1].dropped))
        record = ResearchRecord(planned=planned, ran=state.number, reason=reason, note=note, rounds=rounds)
        self.store.write_artifact(ctx.run_id, "research.json", record)
        if not gap_ran:
            ctx.log.emit("stage.done", "gap", StageDoneData(count=0, seconds=0, skipped=True, round=state.number))
        done = ResearchDoneData(planned=planned, ran=state.number, reason=reason, note=note)
        ctx.log.emit("research.done", "gap", done)

    def end_note(self, reason: StopReason, number: int, *, dropped: bool) -> str:
        if reason == "stopped by user":
            return f"Research stopped by the user after round {number}."
        if reason == "no follow-ups" and dropped:
            return "Every follow-up was dropped by the user."
        return END_NOTES.get(reason, "")

    async def round_pause(self, ctx: steps.StepContext, record: RoundRecord) -> tuple[StopReason | None, RoundRecord]:
        """Ask which follow-ups to search and whether to stop; the plan keeps the answer. No model call.

        Returns the stop reason when the user stopped research or dropped every follow-up.
        """
        asker, state = ctx.asker, ctx.round
        gap = state.gap
        if asker is None or gap is None or not asker.enabled or not self.settings.questions.rounds:
            return None, record
        shown, hidden = gap.queries[:MAX_PAUSE_OPTIONS], gap.queries[MAX_PAUSE_OPTIONS:]
        questions = [
            Question(
                id="q1",
                text="Search these next?",
                kind="multi",
                options=[
                    QuestionOption(id=LETTERS[n], label=query.text, recommended=True) for n, query in enumerate(shown)
                ],
                allow_other=True,
            ),
            Question(
                id="q2",
                text="Stop research here and write?",
                kind="confirm",
                options=[
                    QuestionOption(id="a", label="No, keep going", recommended=True),
                    QuestionOption(id="b", label="Yes, write now"),
                ],
            ),
        ]
        reply = await asker.ask("gap", "round", questions, after=state.number, context=gap.note)
        answers = {answer.question_id: answer for answer in reply.answers}
        if "b" in answers["q2"].option_ids:
            return "stopped by user", record
        chosen = set(answers["q1"].option_ids)
        kept = [query for n, query in enumerate(shown) if LETTERS[n] in chosen] + list(hidden)
        dropped = [query for query in shown if query not in kept]
        plan = ctx.plan()
        extra = (answers["q1"].other or "").strip()
        added: list[Query] = []
        if extra:
            found, rejected = gapping.follow_ups([extra], plan.queries, limit=1)
            added = [query.model_copy(update={"round": state.number + 1}) for query in found]
            self.warnings.extend(f"added query not used: {text} ({why})" for text, why in rejected)
        dropped_ids = {query.id for query in dropped}
        marked = [
            query.model_copy(update={"dropped_by": "user"}) if query.id in dropped_ids else query
            for query in plan.queries
        ]
        ctx.store.write_artifact(ctx.run_id, "plan.json", plan.model_copy(update={"queries": [*marked, *added]}))
        record = record.model_copy(
            update={"dropped": [query.id for query in dropped], "added": [query.id for query in added]}
        )
        return ("no follow-ups" if not kept and not added else None), record

    def stop_before_gap(self, state: steps.RoundState, planned: int) -> StopReason | None:
        if state.number >= planned:
            return "max rounds"
        if state.number > 2 and state.new_pages == 0 and state.previous_new_pages == 0:
            return "no new sources"
        if state.fetched >= self.settings.fetch.max_pages:
            return "page limit reached"
        return None

    def cycle(self, stage: Stage, after: list[Stage]) -> list[Stage]:
        """The stages after `stage` inside the loop, wrapping round once, then the stages after the loop."""
        index = LOOP_STAGES.index(stage)
        return [*LOOP_STAGES[index + 1 :], *LOOP_STAGES[:index], *after]

    def skip(self, ctx: steps.StepContext, stage: Stage) -> None:
        for name in STAGE_ARTIFACTS[stage] if stage != "gap" else ():
            self.store.write_text(ctx.run_id, name, "")
        ctx.log.emit("stage.done", stage, StageDoneData(count=0, seconds=0, skipped=True))

    async def run_stage(
        self, ctx: steps.StepContext, stage: Stage, step: Callable[[Any], Awaitable[steps.Outcome]] | None = None
    ) -> None:
        """Run one stage phase; `step` defaults to the research step of `stage`."""
        step = step or steps.STEPS[stage]
        device = gpu_device(stage, self.settings)
        number = ctx.round.number
        started = StageStartedData(device=device, provider=stage_provider(stage, self.settings), round=number)
        ctx.log.emit("stage.started", stage, started)
        before = self.ledger.total()
        start = time.monotonic()
        timeout = self.settings.run.stage_timeouts[stage]
        try:
            async with asyncio.timeout(timeout):
                outcome = await step(ctx)
        except TimeoutError:
            outcome = self.failed_stage(ctx, stage, f"timed out after {timeout:g} s")
        except Exception as error:
            outcome = self.failed_stage(ctx, stage, str(error) or type(error).__name__)
        ctx.log.flush(stage)
        if outcome.count == 0 and number == 1 and ctx.record.kind == "research":
            files = len(self.store.read_items(ctx.run_id, "files.jsonl", Page))
            if empty_fails(stage, ctx.record.request.sources, files):
                raise StageError(stage, "no output")
        usage = plus(self.ledger.total(), before, -1)
        self.stage_usage[stage] = plus(self.stage_usage.get(stage, Usage()), usage)
        data = StageDoneData(
            count=outcome.count,
            seconds=round(time.monotonic() - start, 3),
            usage=totals(usage),
            provider=outcome.provider or stage_provider(stage, self.settings),
            warnings=[*self.warnings, *outcome.warnings],
            passthrough=outcome.passthrough,
            unfetched=outcome.unfetched,
            filtered=outcome.filtered,
            round=number,
        )
        self.warnings = []
        ctx.log.emit("stage.done", stage, data)

    def failed_stage(self, ctx: steps.StepContext, stage: Stage, error: str) -> steps.Outcome:
        """A failed gap step stops research with a warning; any other failed stage fails the run."""
        if stage != "gap":
            raise StageError(stage, error)
        ctx.round.gap_error = error
        return steps.Outcome(0, warnings=[f"gap failed: {error}"])

    async def release(self, stage: Stage) -> bool:
        """Release the model of a GPU stage's block; false when the block cannot be released."""
        block = GPU_BLOCK.get(stage)
        managed = self.adapters.managed.get(block) if block else None
        if block is None or managed is None or getattr(self.settings, block).release == "none":
            return False
        await managed.release()
        return True

    async def maybe_release(self, ctx: steps.StepContext, stage: Stage, remaining: list[Stage]) -> None:
        if not needs_release(stage, remaining, self.settings):
            return
        block = GPU_BLOCK[stage]
        if block not in self.adapters.managed or getattr(self.settings, block).release == "none":
            return
        following = next_gpu_stage(remaining, self.settings)
        device = gpu_device(stage, self.settings)
        if following is None or device is None:
            return
        data = ResourceData(device=device, released_stage=stage)
        ctx.log.emit("resource.waiting", following, data)
        try:
            await self.release(stage)
        except Exception as error:
            self.warnings.append(f"release of {block} failed: {error}")
        ctx.log.emit("resource.released", following, data)

    def write_costs(self, run_id: str) -> None:
        providers: dict[str, Usage] = {}
        for row in self.ledger.rows():
            providers[row.provider] = plus(providers.get(row.provider, Usage()), row.usage)
        costs = RunCosts(
            stages={stage: totals(usage) for stage, usage in self.stage_usage.items()},
            providers={name: totals(usage) for name, usage in providers.items()},
            total=totals(self.ledger.total()),
        )
        self.store.write_costs(run_id, costs)

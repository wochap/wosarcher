"""Run the stages of a run directory in order: one phase per stage, events, devices, timeouts, and costs.

`Runner.run(run_id)` executes every unfinished stage, so it starts new runs,
resumes, and continues forks the same way.
"""

import asyncio
import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Literal

from wosarcher.config import Settings
from wosarcher.http import Usage, UsageLedger
from wosarcher.models import (
    LOOP_STAGES,
    STAGES,
    Page,
    Plan,
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
from wosarcher.runner import steps
from wosarcher.runner.caches import CachedFetcher
from wosarcher.runner.devices import GPU_BLOCK, gpu_device, needs_release, next_gpu_stage, stage_provider
from wosarcher.runner.events import EventLog, Listener
from wosarcher.runner.preflight import preflight
from wosarcher.store import STAGE_ARTIFACTS, RunStore
from wosarcher.store.caches import PageCache

SKIPPED_BY: dict[Sources, set[Stage]] = {"both": set(), "web": {"load"}, "files": {"search", "fetch"}}
RunEnd = Literal["done", "failed"]
ROUND_STAGES: tuple[Stage, ...] = LOOP_STAGES[:-1]
"""The loop stages every round runs; `gap` follows all but the last."""
LOOP_ARTIFACTS = ("hits.jsonl", "pages.jsonl", "chunks.jsonl", "candidates.jsonl", "scores.jsonl")
NO_NEW_SOURCES = "Follow-up searches returned only pages fetched in earlier rounds."


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

    async def run(self, run_id: str, until: Stage | None = None) -> RunEnd:
        """Run every unfinished stage up to `until`; return `done` or `failed`. Cancellation re-raises."""
        record = self.store.read_record(run_id)
        log = EventLog(self.store, run_id, self.listeners)
        cache = PageCache(self.store.cache_dir / "pages", self.settings.run.page_cache_ttl_hours)
        ctx = steps.StepContext(
            self.store, record, self.settings, self.adapters, log, CachedFetcher(self.adapters.fetcher, cache)
        )
        finished = self.store.finished_stages(run_id)
        last = STAGES.index(until) if until else len(STAGES) - 1
        todo: list[Stage] = [stage for stage in STAGES[: last + 1] if stage not in finished]
        skipped = SKIPPED_BY[record.request.sources]
        runnable: list[Stage] = [stage for stage in todo if stage not in skipped]
        log.emit("run.started", None, self.started(record, until))
        current: Stage | None = None
        if "search" in todo and "plan" not in todo:
            self.restart_loop(run_id)
        try:
            down = await preflight(self.settings, self.adapters.managed, runnable)
            if down:
                raise StageError(*down)
            looped = False
            for stage in todo:
                current = stage
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
                rounds[-1] = rounds[-1].model_copy(update={"note": state.gap.note})
                if state.gap.stop or not state.gap.queries:
                    reason = "model judged coverage sufficient"
            if reason is None:
                state.next()
                ctx.log.round = state.number
        note = {"no new sources": NO_NEW_SOURCES}.get(reason, "")
        if reason == "model judged coverage sufficient" and state.gap is not None:
            note = state.gap.note
        record = ResearchRecord(planned=planned, ran=state.number, reason=reason, note=note, rounds=rounds)
        self.store.write_artifact(ctx.run_id, "research.json", record)
        if not gap_ran:
            ctx.log.emit("stage.done", "gap", StageDoneData(count=0, seconds=0, skipped=True, round=state.number))
        done = ResearchDoneData(planned=planned, ran=state.number, reason=reason, note=note)
        ctx.log.emit("research.done", "gap", done)

    def stop_before_gap(self, state: steps.RoundState, planned: int) -> StopReason | None:
        if state.fetched >= self.settings.fetch.max_pages:
            return "page limit reached"
        if state.number > 1 and state.new_pages == 0:
            return "no new sources"
        if state.number >= planned:
            return "max rounds"
        return None

    def cycle(self, stage: Stage, after: list[Stage]) -> list[Stage]:
        """The stages after `stage` inside the loop, wrapping round once, then the stages after the loop."""
        index = LOOP_STAGES.index(stage)
        return [*LOOP_STAGES[index + 1 :], *LOOP_STAGES[:index], *after]

    def skip(self, ctx: steps.StepContext, stage: Stage) -> None:
        for name in STAGE_ARTIFACTS[stage] if stage != "gap" else ():
            self.store.write_text(ctx.run_id, name, "")
        ctx.log.emit("stage.done", stage, StageDoneData(count=0, seconds=0, skipped=True))

    async def run_stage(self, ctx: steps.StepContext, stage: Stage) -> None:
        device = gpu_device(stage, self.settings)
        number = ctx.round.number
        started = StageStartedData(device=device, provider=stage_provider(stage, self.settings), round=number)
        ctx.log.emit("stage.started", stage, started)
        before = self.ledger.total()
        start = time.monotonic()
        timeout = self.settings.run.stage_timeouts[stage]
        try:
            async with asyncio.timeout(timeout):
                outcome = await steps.STEPS[stage](ctx)
        except TimeoutError:
            outcome = self.failed_stage(ctx, stage, f"timed out after {timeout:g} s")
        except Exception as error:
            outcome = self.failed_stage(ctx, stage, str(error) or type(error).__name__)
        ctx.log.flush(stage)
        if outcome.count == 0 and number == 1:
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

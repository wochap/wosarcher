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
    STAGES,
    Page,
    ResourceData,
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
    UsageTotals,
)
from wosarcher.ports import Adapters
from wosarcher.runner import steps
from wosarcher.runner.caches import CachedFetcher
from wosarcher.runner.devices import GPU_BLOCK, gpu_device, needs_release, next_gpu_stage, stage_provider
from wosarcher.runner.events import EventLog, Listener
from wosarcher.store import STAGE_ARTIFACTS, RunStore
from wosarcher.store.caches import PageCache

SKIPPED_BY: dict[Sources, set[Stage]] = {"both": set(), "web": {"load"}, "files": {"search", "fetch"}}
RunEnd = Literal["done", "failed"]


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
    if stage == "plan":
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
        try:
            for stage in todo:
                current = stage
                if stage in skipped:
                    self.skip(ctx, stage)
                    continue
                await self.run_stage(ctx, stage)
                await self.maybe_release(ctx, stage, runnable[runnable.index(stage) + 1 :])
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

    def skip(self, ctx: steps.StepContext, stage: Stage) -> None:
        for name in STAGE_ARTIFACTS[stage]:
            self.store.write_text(ctx.run_id, name, "")
        ctx.log.emit("stage.done", stage, StageDoneData(count=0, seconds=0, skipped=True))

    async def run_stage(self, ctx: steps.StepContext, stage: Stage) -> None:
        device = gpu_device(stage, self.settings)
        ctx.log.emit(
            "stage.started", stage, StageStartedData(device=device, provider=stage_provider(stage, self.settings))
        )
        before = self.ledger.total()
        start = time.monotonic()
        timeout = self.settings.run.stage_timeouts[stage]
        try:
            async with asyncio.timeout(timeout):
                outcome = await steps.STEPS[stage](ctx)
        except TimeoutError:
            raise StageError(stage, f"timed out after {timeout:g} s") from None
        except Exception as error:
            raise StageError(stage, str(error) or type(error).__name__) from None
        ctx.log.flush(stage)
        if outcome.count == 0:
            files = len(self.store.read_items(ctx.run_id, "files.jsonl", Page))
            if empty_fails(stage, ctx.record.request.sources, files):
                raise StageError(stage, "no output")
        usage = plus(self.ledger.total(), before, -1)
        self.stage_usage[stage] = usage
        data = StageDoneData(
            count=outcome.count,
            seconds=round(time.monotonic() - start, 3),
            usage=totals(usage),
            provider=outcome.provider or stage_provider(stage, self.settings),
            warnings=[*self.warnings, *outcome.warnings],
        )
        self.warnings = []
        ctx.log.emit("stage.done", stage, data)

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

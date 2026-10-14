// The prototype's `done-quick` run: a finished web-only quick run with each stage's seconds.
import type { RunEvent } from "../api/types";
import { ev, stageDone, usage } from "./events";

export const QUICK_SECONDS = {
  plan: 14.4,
  search: 12.9,
  fetch: 10.7,
  chunk: 0.2,
  prefilter: 0.1,
  score: 3.3,
  select: 0.0,
  write: 11.9,
} as const;

export function quickLog(runId = "r1"): RunEvent[] {
  const events: RunEvent[] = [
    ev(
      1,
      "run.started",
      {
        query: "q",
        profile: "low-vram",
        parent_run_id: null,
        version: 1,
        until: null,
      },
      null,
      runId,
    ),
  ];
  let seq = 2;
  events.push({ ...stageDone(seq++, "load", { seconds: 0, skipped: true }), run_id: runId });
  for (const [stage, seconds] of Object.entries(QUICK_SECONDS)) {
    events.push({
      ...ev(seq++, "stage.started", { device: null, provider: null } as never, stage as never),
      run_id: runId,
    });
    events.push({ ...stageDone(seq++, stage, { seconds }), run_id: runId });
  }
  events.push(ev(seq, "run.done", { until: null, totals: usage(0) } as never, null, runId));
  return events;
}

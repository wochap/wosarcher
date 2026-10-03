// Builders for run events in tests and preview fixtures.
import type { RunEvent } from "../api/types";

type Type = RunEvent["type"];
type DataOf<T extends Type> = Extract<RunEvent, { type: T }>["data"];

export function ev<T extends Type>(
  seq: number,
  type: T,
  data: DataOf<T>,
  stage: Extract<RunEvent, { type: T }>["stage"] = null,
  runId = "r1",
): RunEvent {
  return {
    seq,
    type,
    data,
    stage,
    run_id: runId,
    ts: new Date(Date.UTC(2026, 9, 3, 14, 0, seq)).toISOString(),
  } as RunEvent;
}

const usage = (input_tokens: number, output_tokens = 0, cost = 0) => ({
  input_tokens,
  output_tokens,
  cost,
  requests: 1,
  units: 0,
});

export const stageDone = (seq: number, stage: string, extra: Record<string, unknown> = {}) =>
  ev(
    seq,
    "stage.done",
    { count: 1, seconds: 1, usage: usage(0), skipped: false, warnings: [], ...extra } as never,
    stage as never,
  );

export { usage };

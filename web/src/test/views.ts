// A RunView folded from events, for testing the run parts outside the app.
import type { RunEvent } from "../api/types";
import { initialRunView, type RunView, runReducer } from "../run/reducer";

export const viewOf = (events: RunEvent[], runId = events[0]?.run_id ?? "r1"): RunView =>
  events.reduce(runReducer, initialRunView(runId));

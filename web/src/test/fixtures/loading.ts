// Scenario `loading`: the run is queued, waiting for a free worker.
import { ev } from "../events";
import { type Fixture, otherRuns, RUN_ID, summary } from "./sample";

export const loading: Fixture = {
  screen: "live",
  runId: RUN_ID,
  data: {
    runs: [summary({ status: "queued", duration_s: null, cost: null }), ...otherRuns],
    events: { [RUN_ID]: [ev(0, "run.queued", { position: 1 }, null, RUN_ID)] },
  },
};

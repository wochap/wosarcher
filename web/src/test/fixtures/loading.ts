// Scenario `loading`: the event socket is opening and no `run.queued` has arrived yet.
import { type Fixture, otherRuns, RUN_ID, summary } from "./sample";

export const loading: Fixture = {
  screen: "live",
  runId: RUN_ID,
  data: {
    runs: [summary({ status: "queued", duration_s: null, cost: null }), ...otherRuns],
    events: { [RUN_ID]: [] },
  },
};

// Scenario `live`: the sample run streaming from start to Completed.
import {
  artifacts,
  type Fixture,
  MD1,
  otherRuns,
  RUN_ID,
  researchEvents,
  sourceViews,
  summary,
} from "./sample";

export const live: Fixture = {
  screen: "live",
  runId: RUN_ID,
  stream: "timer",
  data: {
    runs: [summary({ status: "running", duration_s: null, cost: null }), ...otherRuns],
    events: { [RUN_ID]: researchEvents(RUN_ID) },
    artifacts: { [RUN_ID]: artifacts(MD1, "numeric") },
    sources: { [RUN_ID]: sourceViews() },
  },
};

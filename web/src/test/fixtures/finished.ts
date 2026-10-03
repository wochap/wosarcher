// Scenario `finished`: the Report screen of the completed sample run.
import { artifacts, type Fixture, MD1, otherRuns, RUN_ID, researchEvents, summary } from "./sample";

export const finished: Fixture = {
  screen: "report",
  runId: RUN_ID,
  data: {
    runs: [summary(), ...otherRuns],
    events: { [RUN_ID]: researchEvents(RUN_ID) },
    artifacts: { [RUN_ID]: artifacts(MD1, "numeric") },
  },
};

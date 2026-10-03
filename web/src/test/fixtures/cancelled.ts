// Scenario `cancelled`: the run is cancelled while fetch runs, before scoring and writing.
import {
  type Fixture,
  followedBy,
  otherRuns,
  RUN_ID,
  researchEvents,
  summary,
  upTo,
} from "./sample";

let pages = 0;
const events = followedBy(
  upTo(
    researchEvents(RUN_ID),
    (e) => (e.type === "page.fetched" || e.type === "page.failed") && ++pages === 9,
  ),
  ["run.cancelled", { stage: "fetch" }, null],
);

export const cancelled: Fixture = {
  screen: "live",
  runId: RUN_ID,
  data: {
    runs: [summary({ status: "cancelled", duration_s: 40, cost: 0 }), ...otherRuns],
    events: { [RUN_ID]: events },
  },
};

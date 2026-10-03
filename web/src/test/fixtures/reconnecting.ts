// Scenario `reconnecting`: the socket drops during fetch, fails once more, then replays.
import {
  artifacts,
  type Fixture,
  MD1,
  otherRuns,
  RUN_ID,
  researchEvents,
  summary,
  upTo,
} from "./sample";

const events = upTo(
  researchEvents(RUN_ID),
  (e) => e.type === "stage.started" && e.stage === "score",
);
const firstFetched = events.findIndex((e) => e.type === "page.fetched");

export const reconnecting: Fixture = {
  screen: "live",
  runId: RUN_ID,
  stream: "drop",
  dropAt: events[firstFetched + 12].seq,
  data: {
    runs: [summary({ status: "running", duration_s: null, cost: null }), ...otherRuns],
    events: { [RUN_ID]: events },
    artifacts: { [RUN_ID]: artifacts(MD1, "numeric") },
  },
};

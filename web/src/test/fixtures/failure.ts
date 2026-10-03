// Scenario `failure`: the scorer runs out of GPU memory while scoring the third query.
import {
  artifacts,
  ERR,
  type Fixture,
  followedBy,
  MD1,
  otherRuns,
  RUN_ID,
  researchEvents,
  summary,
  upTo,
} from "./sample";

let scored = 0;
const events = followedBy(
  upTo(researchEvents(RUN_ID), (e) => e.type === "passages.scored" && ++scored === 3),
  ["stage.failed", { error: ERR, next: "" }, "score"],
  ["run.failed", { stage: "score", error: ERR }, null],
);

export const failure: Fixture = {
  screen: "live",
  runId: RUN_ID,
  data: {
    runs: [summary({ status: "failed", duration_s: 76, cost: 0 }), ...otherRuns],
    events: { [RUN_ID]: events },
    artifacts: { [RUN_ID]: artifacts(MD1, "numeric") },
  },
};

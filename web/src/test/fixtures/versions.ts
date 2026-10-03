// Scenario `versions`: v2 (`r_8c4e`), a rewrite of the sample run, shorter and concise.
import { writing } from "./data";
import {
  artifacts,
  type Fixture,
  Log,
  MD1,
  MD2,
  otherRuns,
  QUERY,
  RUN_ID,
  researchEvents,
  summary,
  writeEvents,
} from "./sample";

export const REWRITE_ID = "r_8c4e";
const COPIED = ["plan", "search", "load", "fetch", "chunk", "prefilter", "score", "select"];
const COUNTS: Record<string, number> = {
  plan: 5,
  search: 22,
  load: 2,
  fetch: 19,
  chunk: 412,
  prefilter: 96,
  score: 96,
  select: 14,
};

function rewriteEvents() {
  const log = new Log(REWRITE_ID);
  log.add("run.started", {
    query: QUERY,
    profile: "low-vram",
    parent_run_id: RUN_ID,
    until: null,
    version: 2,
  });
  for (const stage of COPIED) log.done(stage, COUNTS[stage], { copied_from: RUN_ID });
  writeEvents(log, MD2);
  return log.events;
}

export const versions: Fixture = {
  screen: "report",
  runId: REWRITE_ID,
  data: {
    runs: [
      summary({
        run_id: REWRITE_ID,
        created: "2026-10-03T14:09:00Z",
        parent_run_id: RUN_ID,
        fork_from: "write",
        version: 2,
        writing: { ...writing, tone: "concise", words: 250, citation_marker: "superscript" },
        duration_s: 51,
      }),
      summary(),
      ...otherRuns,
    ],
    events: { [RUN_ID]: researchEvents(RUN_ID), [REWRITE_ID]: rewriteEvents() },
    artifacts: {
      [RUN_ID]: artifacts(MD1, "numeric"),
      [REWRITE_ID]: artifacts(MD2, "superscript"),
    },
  },
};

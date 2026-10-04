// A multi-round run's event log for tests: three planned rounds, cut at any point.
import type { RunEvent } from "../api/types";
import { ev, stageDone } from "./events";

type Ending = "coverage" | "nonew" | "max";

const LOOP = ["search", "fetch", "chunk", "prefilter", "score"] as const;
const PLANNER = ["a", "b", "c", "d", "e"].map((text, i) => ({ id: `q${i + 1}`, text }));

/** Round k's stage events, with one hit per query and `pages` fetched pages. */
function round(seq: number, k: number, ids: string[], pages: number, known: number): RunEvent[] {
  const out: RunEvent[] = [];
  for (const stage of LOOP) {
    out.push(ev(seq++, "stage.started", { device: null, provider: "x", round: k }, stage));
    if (stage === "search")
      for (const id of ids)
        out.push(ev(seq++, "hit.found", { url: `https://${id}.test`, title: id, query_ids: [id] }));
    if (stage === "fetch")
      for (let n = 0; n < pages; n++) {
        const url = `https://r${k}-${n}.test`;
        const data = {
          url,
          source_id: `s${k}${n}`,
          title: url,
          chars: 10,
          cached: false,
          round: k,
        };
        out.push(ev(seq++, "page.fetched", data, "fetch"));
      }
    out.push(stageDone(seq++, stage, { round: k }));
  }
  const done = { round: k, query_ids: ids, new_pages: pages, known_pages: known, kept: pages * 2 };
  out.push(ev(seq++, "round.done", done, "score"));
  return out;
}

/** The whole log; `ending` picks how research stops. */
export function roundsLog(ending: Ending = "coverage"): RunEvent[] {
  const log: RunEvent[] = [
    ev(1, "run.started", {
      query: "q",
      profile: "p",
      parent_run_id: null,
      version: 1,
      until: null,
    }),
    ev(2, "stage.started", { device: null, provider: "llm", round: 1 }, "plan"),
    ev(3, "plan.ready", { queries: [{ id: "q0", text: "q" }, ...PLANNER] }),
    stageDone(4, "plan"),
  ];
  const next = () => (log.at(-1)?.seq ?? 0) + 1;
  type Follow = { id: string; text: string; round?: number };
  const gap = (k: number, queries: Follow[], stop: boolean, note: string) => {
    log.push(ev(next(), "stage.started", { device: null, provider: "llm", round: k }, "gap"));
    log.push(ev(next(), "gap.ready", { round: k, queries, note, stop }, "gap"));
    log.push(stageDone(next(), "gap", { round: k, count: queries.length }));
  };
  log.push(
    ...round(
      next(),
      1,
      PLANNER.map((q) => q.id),
      16,
      0,
    ),
  );
  const second = [
    { id: "q6", text: "f", round: 2 },
    { id: "q7", text: "g", round: 2 },
  ];
  gap(1, second, false, "Missing: benchmarks.");
  if (ending === "nonew") {
    log.push(...round(next(), 2, ["q6", "q7"], 0, 9));
    const reason = "no new sources";
    const note = "Follow-up searches returned only pages fetched in earlier rounds.";
    log.push(ev(next(), "research.done", { planned: 3, ran: 2, reason, note }, "gap"));
    return log;
  }
  log.push(...round(next(), 2, ["q6", "q7"], 6, 0));
  if (ending === "coverage") {
    gap(2, [], true, "Every sub-query has primary sources.");
    const reason = "model judged coverage sufficient";
    const note = "Every sub-query has primary sources.";
    log.push(ev(next(), "research.done", { planned: 3, ran: 2, reason, note }, "gap"));
    return log;
  }
  gap(2, [{ id: "q8", text: "h", round: 3 }], false, "Missing: latency.");
  log.push(...round(next(), 3, ["q8"], 4, 0));
  log.push(
    ev(next(), "research.done", { planned: 3, ran: 3, reason: "max rounds", note: "" }, "gap"),
  );
  return log;
}

/** The log up to (not including) the first event that matches. */
export const until = (log: RunEvent[], stop: (e: RunEvent) => boolean) => {
  const end = log.findIndex(stop);
  return end < 0 ? log : log.slice(0, end);
};

/** Round 2 fetching: the log up to round 2's fetch `stage.done`. */
export const roundTwoFetching = () =>
  until(
    roundsLog("max"),
    (e) => e.type === "stage.done" && e.stage === "fetch" && e.data.round === 2,
  );

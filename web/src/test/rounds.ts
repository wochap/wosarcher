// A multi-round run's event log for tests: three planned rounds, cut at any point.
import type { RunEvent } from "../api/types";
import type { StopReason } from "../run/reducer";
import { ev, stageDone } from "./events";

type Ending = "nofollow" | "nonew" | "max";

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

/** The whole log; `ending` picks how research stops. `nonew` plans four rounds, the others three. */
export function roundsLog(ending: Ending = "nofollow"): RunEvent[] {
  const planned = ending === "nonew" ? 4 : 3;
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
  const gap = (
    k: number,
    queries: Follow[],
    uncovered: string[],
    note: string,
    missing: string[] = [],
  ) => {
    const retried = !queries.length;
    log.push(ev(next(), "stage.started", { device: null, provider: "llm", round: k }, "gap"));
    log.push(
      ev(next(), "gap.ready", { round: k, queries, note, uncovered, missing, retried }, "gap"),
    );
    log.push(stageDone(next(), "gap", { round: k, count: queries.length }));
  };
  const done = (ran: number, reason: StopReason, note: string) =>
    log.push(ev(next(), "research.done", { planned, ran, reason, note }, "gap"));
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
  gap(1, second, ["q4", "q5"], "Benchmarks are thin.", ["setup", "cost"]);
  const third = [{ id: "q8", text: "h", round: 3 }];
  if (ending === "nonew") {
    log.push(...round(next(), 2, ["q6", "q7"], 0, 9));
    gap(2, third, ["q6", "q7"], "Vendor data is thin.");
    log.push(...round(next(), 3, ["q8"], 0, 3));
    done(3, "no new sources", "Follow-up searches returned only pages fetched in earlier rounds.");
    return log;
  }
  log.push(...round(next(), 2, ["q6", "q7"], 6, 0));
  if (ending === "nofollow") {
    gap(2, [], ["q6", "q7"], "Latency is unclear.");
    done(2, "no follow-ups", "The gap step wrote no usable follow-up query.");
    return log;
  }
  gap(2, third, [], "Latency is unclear.");
  log.push(...round(next(), 3, ["q8"], 4, 0));
  done(3, "max rounds", "");
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

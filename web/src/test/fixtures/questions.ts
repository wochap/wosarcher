// Scenarios `live-clarify`, `live-clarify-idle`, `live-round-input`, and `finished-timeout`: runs
// that ask questions, after the prototype's Peru example. Also the pauses the tests build on.
import type { Question, RunEvent, RunSummary } from "../../api/types";
import { ev, usage } from "../events";
import { roundsLog, until } from "../rounds";
import { type Fixture, followedBy, otherRuns, RUN_ID, summary } from "./sample";

export const PERU =
  "Map the structure of Peru’s executive branch: the ministries, their main attached agencies and who currently heads each one, with official links.";
export const TOPIC = "Peru executive branch: ministries, attached agencies, current heads";
const SUB_QUERIES = [
  "Peru ministerios lista oficial gob.pe",
  "Presidencia del Consejo de Ministros organigrama",
  "organismos públicos adscritos por ministerio Perú",
  "ROF ministerios Perú estructura orgánica",
  "Peru cabinet ministers 2026",
];

type Option = [label: string, description?: string, recommended?: boolean];

function question(
  id: string,
  kind: Question["kind"],
  text: string,
  options: Option[],
  other = false,
) {
  return {
    id,
    kind,
    text,
    allow_other: other,
    options: options.map(([label, description, recommended], i) => ({
      id: `o${i + 1}`,
      label,
      ...(description ? { description } : {}),
      recommended: !!recommended,
    })),
  } as Question;
}

/** The four questions asked before searching. */
export const CLARIFY: Question[] = [
  question("q1", "confirm", "Include regional and local governments?", [
    ["Yes, at summary depth", "One row per regional government, no agencies below it.", true],
    ["No", "National executive only."],
  ]),
  question(
    "q2",
    "multi",
    "Which sources should dominate?",
    [
      ["gob.pe and official sites", "Ministry portals, El Peruano, PCM.", true],
      ["Wikipedia"],
      ["News"],
    ],
    true,
  ),
  question("q3", "single", "How deep for attached agencies?", [
    ["Main agencies per ministry", "Up to five per ministry.", true],
    ["Every listed agency", "Slower: about 200 more pages."],
    ["Skip agencies"],
  ]),
  question("q4", "confirm", "Verify current office holders with a dated source?", [
    ["Yes", "Each head needs a source from the last 90 days.", true],
    ["No"],
  ]),
];

const FOLLOW_UPS = [
  'site:gob.pe "ministro" designación resolución suprema 2026',
  "El Peruano resolución suprema designa ministro",
  "gob.pe/institucion ministerio enlaces oficiales",
];

/** The questions asked after round 2: the follow-up searches, and whether to stop. */
export const ROUND: Question[] = [
  question(
    "q1",
    "multi",
    "Search these next?",
    FOLLOW_UPS.map((label) => [label, undefined, true] as Option),
    true,
  ),
  question("q2", "confirm", "Stop research here and write?", [
    ["No, keep going", undefined, true],
    ["Yes, write now", "Writes from the passages kept so far."],
  ]),
];

export type NeededOptions = {
  pauseId?: number;
  timeout?: number;
  after?: number;
  context?: string;
};

/** An `input.needed` for a clarify pause (stage `plan`) or a round pause (stage `gap`). */
export function needed(
  seq: number,
  kind: "clarify" | "round",
  o: NeededOptions = {},
  stage?: string,
) {
  const clarify = kind === "clarify";
  return ev(
    seq,
    "input.needed",
    {
      pause_id: o.pauseId ?? 1,
      kind,
      ...(clarify ? {} : { after: o.after ?? 2 }),
      context:
        o.context ??
        (clarify
          ? `I read the brief as: ${TOPIC}`
          : "Still missing: current ministers for most ministries and official links."),
      questions: clarify ? CLARIFY : ROUND,
      created: new Date(Date.UTC(2026, 9, 3, 14, 0, seq)).toISOString(),
      timeout: o.timeout ?? 60,
      max_wait: 1800,
    },
    (stage ?? (clarify ? "plan" : "gap")) as never,
    RUN_ID,
  );
}

/** An `input.answered` with `count` answers. */
export function answeredEvent(
  seq: number,
  by: "user" | "agent" | "timeout",
  count: number,
  o: { pauseId?: number; seconds?: number } = {},
  stage?: string,
) {
  const answers = Array.from({ length: count }, (_, i) => ({
    question_id: `q${i + 1}`,
    option_ids: ["o1"],
  }));
  return ev(
    seq,
    "input.answered",
    { pause_id: o.pauseId ?? 1, answers, answered_by: by, seconds_waited: o.seconds ?? 60 },
    (stage ?? null) as never,
    RUN_ID,
  );
}

/** The Peru run up to the clarify pause: started, planned, waiting for the user. */
export function clarifyLog(o: NeededOptions = {}): RunEvent[] {
  const start = ev(
    1,
    "run.started",
    { query: PERU, profile: "low-vram", parent_run_id: null, until: null, version: 1 },
    null,
    RUN_ID,
  );
  const plan = ev(2, "stage.started", { device: null, provider: "llama.cpp" }, "plan", RUN_ID);
  const ready = ev(
    3,
    "plan.ready",
    { queries: SUB_QUERIES.map((text, i) => ({ id: `q${i + 1}`, text })) },
    "plan",
    RUN_ID,
  );
  return [start, plan, ready, needed(4, "clarify", o)];
}

/** The three-round Peru run with the pause after round 2's gap step, open. */
export function roundLog(o: NeededOptions = {}): RunEvent[] {
  const log = roundsLog("max").map((e) => ({ ...e, run_id: RUN_ID }));
  const gap = until(log, (e) => e.type === "stage.done" && e.stage === "gap" && e.data.round === 2);
  const head = gap.map((e) =>
    e.type === "run.started" ? ({ ...e, data: { ...e.data, query: PERU } } as RunEvent) : e,
  );
  return followedBy(head, ["input.needed", needed(0, "round", o).data, "gap"]);
}

/** The whole three-round run, finished, whose round 2 pause timed out. */
export function timeoutLog(): RunEvent[] {
  const log = roundsLog("max").map((e) => ({ ...e, run_id: RUN_ID }));
  const at = log.findIndex(
    (e) => e.type === "stage.done" && e.stage === "gap" && e.data.round === 2,
  );
  const pause = needed(0, "round", { timeout: 60 });
  const answered = answeredEvent(0, "timeout", 2, { seconds: 60 }, "gap");
  const merged = [...log.slice(0, at), pause, answered, ...log.slice(at)].map((e, i) => ({
    ...e,
    seq: i + 1,
  }));
  const named = merged.map((e) =>
    e.type === "run.started" ? ({ ...e, data: { ...e.data, query: PERU } } as RunEvent) : e,
  );
  return followedBy(named, ["run.done", { totals: usage(0), until: null }, null]);
}

const waitingRun = (extra: Partial<RunSummary> = {}) =>
  summary({ status: "waiting", query: PERU, duration_s: null, cost: null, ...extra });

export const liveClarify: Fixture = {
  screen: "live",
  runId: RUN_ID,
  data: { runs: [waitingRun(), ...otherRuns], events: { [RUN_ID]: clarifyLog() } },
};

/** The same pause; stop interacting for 10 seconds and the chip counts down from 1:00. */
export const liveClarifyIdle: Fixture = liveClarify;

export const liveRoundInput: Fixture = {
  screen: "live",
  runId: RUN_ID,
  data: {
    runs: [waitingRun({ rounds_planned: 3 }), ...otherRuns],
    events: { [RUN_ID]: roundLog() },
  },
};

export const finishedTimeout: Fixture = {
  screen: "live",
  runId: RUN_ID,
  data: {
    runs: [summary({ query: PERU, rounds_planned: 3, rounds_ran: 3 }), ...otherRuns],
    events: { [RUN_ID]: timeoutLog() },
  },
};

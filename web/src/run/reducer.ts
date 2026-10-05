// One run's view state, folded from its event stream. Pure: the same reducer serves live runs,
// reconnects, and finished runs (a finished run is its replayed event log).
import { ENDED, LIVE_ONLY, TERMINAL } from "../api/events";
import type * as G from "../api/generated";
import type { KeptPassage, RunDetail, RunEvent, RunStatus, Stage } from "../api/types";

/** The prototype's phases, in display order. The initial search runs inside `plan`; `gap` shows
 * only for multi-round runs. */
export const PHASES = [
  "plan",
  "search",
  "fetch",
  "load",
  "chunk",
  "prefilter",
  "score",
  "gap",
  "select",
  "write",
] as const satisfies readonly Stage[];
export type PhaseId = (typeof PHASES)[number];

/** The stages that repeat once per research round, gap included. */
export const LOOP_PHASES: readonly PhaseId[] = [
  "search",
  "fetch",
  "chunk",
  "prefilter",
  "score",
  "gap",
];

export type PhaseState =
  | "pending"
  | "waiting"
  | "running"
  | "done"
  | "reused"
  | "failed"
  | "cancelled";

export type Phase = {
  state: PhaseState;
  counters: Record<string, number>;
  device?: string;
  waitReason?: string;
  skipped?: boolean;
  copiedFrom?: string;
  error?: string;
  /** From `stage.started`: `<provider>:<model>`, or `<provider>`. */
  configuredProvider?: string;
  /** From `stage.done`: what actually ran, in the same form. */
  provider?: string;
  warnings: string[];
  /** The research round of the last `stage.*` event; 1 outside the loop. */
  round: number;
  /** Rounds this stage finished (not skipped). */
  roundsDone: number;
};

export type StopReason = G.ResearchDoneData["reason"];

export type RoundQuery = { id: string; text: string; results: number; searched: boolean };

export type RoundView = {
  round: number;
  queries: RoundQuery[];
  /** `queued` until its search starts. */
  state: "queued" | "running" | "done" | "cancelled";
  /** The loop stage the round is in while running. */
  stage?: Stage;
  newPages: number;
  knownPages: number;
  kept: number;
  /** The gap note written after this round. */
  note: string;
  /** The gap step after this round: running, or the follow-up count it wrote. */
  gap?: "running" | number;
  /** Query IDs the gap step's coverage table marked `uncovered`. */
  uncovered: string[];
};

export type ResearchView = { planned: number; ran: number; reason: StopReason; note: string };

export type SubQuery = { id: string; text: string; results: number; done: boolean };

export type SourceView = {
  sourceId: string;
  kind: "web" | "file";
  title: string;
  uri: string;
  state: "found" | "fetched" | "failed";
  reason?: string;
  kept: number;
  /** Fetched by the run this fork copied the fetch stage from. */
  cached?: boolean;
  /** The research round that fetched it. */
  round: number;
};

export type ScoredQuery = {
  queryId: string;
  scorer: string;
  threshold: number | null;
  scored: number;
  kept: number;
  items: KeptPassage[];
};

export type RunView = {
  runId: string;
  lastSeq: number;
  status: RunStatus;
  query?: string;
  profile?: string;
  parentRunId?: string | null;
  version?: number;
  until?: Stage | null;
  queuePosition?: number;
  startedAt?: string;
  endedAt?: string;
  failure?: { stage: string; error: string };
  phases: Record<PhaseId, Phase>;
  subQueries: SubQuery[];
  /** Hits per query ID that arrived before `plan.ready` listed the query (the initial search). */
  earlyHits: Record<string, number>;
  /** Research rounds that started, from `plan.ready` on; round 1 holds the planner's queries. */
  rounds: RoundView[];
  /** From `research.done`; null until research ends (and for single-round runs). */
  research: ResearchView | null;
  /** Keyed by URL (web) or path (file). */
  sources: Record<string, SourceView>;
  passages: ScoredQuery[];
  /** Sub-query IDs that skipped prefilter ranking (small-input passthrough). */
  passthrough: string[];
  /** Search hits the domain filter dropped, summed over the plan and search stages of every round. */
  filtered: number;
  report: string;
  tokensIn: number;
  tokensOut: number;
  cost: number;
};

export function initialRunView(runId: string): RunView {
  const phases = {} as Record<PhaseId, Phase>;
  for (const id of PHASES)
    phases[id] = { state: "pending", counters: {}, warnings: [], round: 1, roundsDone: 0 };
  return {
    runId,
    lastSeq: 0,
    status: "queued",
    phases,
    subQueries: [],
    earlyHits: {},
    rounds: [],
    research: null,
    sources: {},
    passages: [],
    passthrough: [],
    filtered: 0,
    report: "",
    tokensIn: 0,
    tokensOut: 0,
    cost: 0,
  };
}

function isPhase(stage: string | null | undefined): stage is PhaseId {
  return !!stage && (PHASES as readonly string[]).includes(stage);
}

function withPhase(state: RunView, stage: string | null | undefined, patch: Partial<Phase>) {
  if (!isPhase(stage)) return state;
  return { ...state, phases: { ...state.phases, [stage]: { ...state.phases[stage], ...patch } } };
}

function withSource(state: RunView, key: string, patch: Partial<SourceView>): RunView {
  const current: SourceView = state.sources[key] ?? {
    sourceId: "",
    kind: "web",
    title: key,
    uri: key,
    state: "found",
    kept: 0,
    round: 1,
  };
  return { ...state, sources: { ...state.sources, [key]: { ...current, ...patch } } };
}

function stopRunning(state: RunView, to: PhaseState): RunView {
  const phases = { ...state.phases };
  for (const id of PHASES) {
    if (phases[id].state === "running" || phases[id].state === "waiting") {
      phases[id] = { ...phases[id], state: to };
    }
  }
  const rounds = state.rounds.map((r) =>
    r.state === "running"
      ? { ...r, state: "cancelled" as const, gap: r.gap === "running" ? undefined : r.gap }
      : r,
  );
  return { ...state, phases, rounds };
}

function withRound(state: RunView, round: number, patch: Partial<RoundView>): RunView {
  if (!state.rounds.some((r) => r.round === round)) return state;
  return {
    ...state,
    rounds: state.rounds.map((r) => (r.round === round ? { ...r, ...patch } : r)),
  };
}

const newRound = (
  round: number,
  queries: { id: string; text: string }[],
  hits: Record<string, number> = {},
): RoundView => ({
  round,
  queries: queries.map((q) => ({
    id: q.id,
    text: q.text,
    results: hits[q.id] ?? 0,
    searched: false,
  })),
  state: "queued",
  newPages: 0,
  knownPages: 0,
  kept: 0,
  note: "",
  uncovered: [],
});

const isLoop = (stage: string | null | undefined): stage is PhaseId =>
  !!stage && LOOP_PHASES.includes(stage as PhaseId);

/** A loop stage's start moves its round to that stage; the gap step marks the round it follows. */
function roundStarted(state: RunView, stage: PhaseId, round: number): RunView {
  if (!state.rounds.length) return state;
  if (stage === "gap") return withRound(state, round, { gap: "running" });
  const known = state.rounds.some((r) => r.round === round);
  const rounds = known ? state.rounds : [...state.rounds, newRound(round, [])];
  return withRound({ ...state, rounds }, round, { state: "running", stage });
}

function apply(state: RunView, event: RunEvent): RunView {
  switch (event.type) {
    case "run.queued":
      return { ...state, status: "queued", queuePosition: event.data.position };
    case "run.started": {
      const d = event.data;
      return {
        ...state,
        status: "running",
        startedAt: event.ts,
        query: d.query,
        profile: d.profile,
        parentRunId: d.parent_run_id,
        version: d.version,
        until: d.until,
        queuePosition: undefined,
      };
    }
    case "run.done":
      return { ...state, status: "done", endedAt: event.ts };
    case "run.failed": {
      const stage = event.data.stage ?? "";
      const failed = withPhase(state, stage, { state: "failed", error: event.data.error });
      return {
        ...stopRunning(failed, "cancelled"),
        status: "failed",
        endedAt: event.ts,
        failure: { stage, error: event.data.error },
      };
    }
    case "run.cancelled":
      return { ...stopRunning(state, "cancelled"), status: "cancelled", endedAt: event.ts };
    case "stage.started": {
      const round = event.data.round ?? 1;
      const next = withPhase(state, event.stage, {
        state: "running",
        device: event.data.device ?? undefined,
        configuredProvider: event.data.provider ?? undefined,
        waitReason: undefined,
        round,
      });
      return isLoop(event.stage) ? roundStarted(next, event.stage, round) : next;
    }
    case "stage.progress": {
      const { done, total, failed } = event.data;
      return withPhase(state, event.stage, {
        counters: { done, total, failed },
        round: event.data.round ?? 1,
      });
    }
    case "stage.done": {
      const d = event.data;
      const usage = d.usage ?? { input_tokens: 0, output_tokens: 0, cost: 0 };
      const phase = isPhase(event.stage) ? state.phases[event.stage] : undefined;
      const round = d.round ?? 1;
      let next = withPhase(state, event.stage, {
        state: d.copied_from ? "reused" : "done",
        copiedFrom: d.copied_from ?? undefined,
        skipped: d.skipped ?? false,
        counters: { ...phase?.counters, count: d.count },
        provider: d.provider ?? undefined,
        warnings: d.warnings ?? [],
        round,
        roundsDone: (phase?.roundsDone ?? 0) + (d.skipped || d.copied_from ? 0 : 1),
      });
      if (event.stage === "prefilter") {
        const earlier = round > 1 ? state.passthrough : [];
        next = { ...next, passthrough: [...earlier, ...(d.passthrough ?? [])] };
      }
      if (event.stage === "search" || event.stage === "plan") {
        next = { ...next, filtered: next.filtered + (d.filtered ?? 0) };
        next = { ...next, subQueries: next.subQueries.map((q) => ({ ...q, done: true })) };
      }
      if (event.stage === "search") {
        const searched = next.rounds.find((r) => r.round === round)?.queries;
        next = withRound(next, round, {
          queries: searched?.map((q) => ({ ...q, searched: true })),
        });
      }
      return {
        ...next,
        tokensIn: state.tokensIn + (usage.input_tokens ?? 0),
        tokensOut: state.tokensOut + (usage.output_tokens ?? 0),
        cost: state.cost + (usage.cost ?? 0),
      };
    }
    case "stage.failed":
      return withPhase(state, event.stage, { state: "failed", error: event.data.error });
    case "resource.waiting":
      return withPhase(state, event.stage, {
        state: "waiting",
        device: event.data.device,
        waitReason: `${event.data.released_stage} unloading`,
      });
    case "resource.released":
      return state;
    case "plan.ready": {
      const { queries } = event.data;
      const hits = state.earlyHits;
      return {
        ...state,
        subQueries: queries.map((q) => ({
          id: q.id,
          text: q.text,
          results: hits[q.id] ?? 0,
          done: false,
        })),
        earlyHits: {},
        rounds: [newRound(1, queries, hits)],
        research: null,
      };
    }
    case "hit.found": {
      const { url, title, query_ids } = event.data;
      const listed = new Set(state.subQueries.map((q) => q.id));
      const earlyHits = { ...state.earlyHits };
      for (const id of query_ids) if (!listed.has(id)) earlyHits[id] = (earlyHits[id] ?? 0) + 1;
      const phase = isPhase(event.stage) ? state.phases[event.stage] : undefined;
      const counted = phase
        ? withPhase(state, event.stage, {
            counters: { ...phase.counters, hits: (phase.counters.hits ?? 0) + 1 },
          })
        : state;
      const subQueries = state.subQueries.map((q) =>
        query_ids.includes(q.id) ? { ...q, results: q.results + 1 } : q,
      );
      const rounds = state.rounds.map((r) => ({
        ...r,
        queries: r.queries.map((q) =>
          query_ids.includes(q.id) ? { ...q, results: q.results + 1 } : q,
        ),
      }));
      const known = state.sources[url];
      return withSource(
        { ...counted, subQueries, rounds, earlyHits },
        url,
        known
          ? {}
          : {
              title,
              uri: url,
            },
      );
    }
    case "page.fetched": {
      const d = event.data;
      const round = d.round ?? 1;
      const current = state.rounds.find((r) => r.round === round);
      const counted = current ? withRound(state, round, { newPages: current.newPages + 1 }) : state;
      return withSource(counted, d.url, {
        round,
        sourceId: d.source_id,
        title: d.title || state.sources[d.url]?.title || d.url,
        uri: d.url,
        kind: event.stage === "load" ? "file" : "web",
        state: "fetched",
        reason: undefined,
      });
    }
    case "page.failed":
      return withSource(state, event.data.url, { state: "failed", reason: event.data.reason });
    case "passages.scored": {
      const d = event.data;
      const sources = { ...state.sources };
      for (const passage of d.passages) {
        const key = Object.keys(sources).find((k) => sources[k].sourceId === passage.source_id);
        if (key) sources[key] = { ...sources[key], kept: sources[key].kept + 1 };
      }
      const scored: ScoredQuery = {
        queryId: d.query_id,
        scorer: d.scorer,
        threshold: d.threshold_display ?? null,
        scored: d.scored,
        kept: d.kept,
        items: d.passages,
      };
      return { ...state, sources, passages: [...state.passages, scored] };
    }
    case "round.done": {
      const d = event.data;
      return withRound(state, d.round, {
        state: "done",
        stage: undefined,
        newPages: d.new_pages,
        knownPages: d.known_pages,
        kept: d.kept,
      });
    }
    case "gap.ready": {
      const d = event.data;
      const next = withRound(state, d.round, {
        gap: d.queries.length,
        note: d.note,
        uncovered: d.uncovered,
      });
      if (!d.queries.length) return next;
      const following = newRound(d.round + 1, d.queries);
      return { ...next, rounds: [...next.rounds, following] };
    }
    case "research.done": {
      const d = event.data;
      const rounds = state.rounds
        .filter((r) => r.round <= d.ran)
        .map((r) => ({ ...r, gap: r.gap === "running" ? undefined : r.gap }));
      const research = { planned: d.planned, ran: d.ran, reason: d.reason, note: d.note };
      return { ...state, rounds, research };
    }
    case "report.delta":
      return { ...state, report: state.report + event.data.text };
    case "report.snapshot":
      return { ...state, report: event.data.text };
  }
}

export function runReducer(state: RunView, event: RunEvent): RunView {
  if (LIVE_ONLY.has(event.type)) return apply(state, event);
  // A terminal event that is not logged carries a seq already applied (0 when nothing was logged).
  if (TERMINAL.has(event.type)) {
    if (isEnded(state.status) && state.lastSeq >= event.seq) return state;
    return { ...apply(state, event), lastSeq: Math.max(state.lastSeq, event.seq) };
  }
  if (event.seq <= state.lastSeq) return state;
  return { ...apply(state, event), lastSeq: event.seq };
}

export function isEnded(status: RunStatus): boolean {
  return ENDED.has(status);
}

/** What a run summary (or a cancel's 409 answer) says about how the run ended. */
export type RunEnd = Pick<RunDetail, "status"> & Partial<Pick<RunDetail, "error" | "end_stage">>;

/** Sets an ended status from the server's summary on a view that still shows the run open. */
export function applySummary(state: RunView, summary: RunEnd): RunView {
  if (!isEnded(summary.status) || isEnded(state.status)) return state;
  if (summary.status === "failed") {
    const stage = summary.end_stage ?? "";
    const error = summary.error ?? "";
    const failed = withPhase(state, stage, { state: "failed", error });
    return { ...stopRunning(failed, "cancelled"), status: "failed", failure: { stage, error } };
  }
  if (summary.status === "cancelled") {
    return { ...stopRunning(state, "cancelled"), status: "cancelled" };
  }
  return { ...state, status: summary.status };
}

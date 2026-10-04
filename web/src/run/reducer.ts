// One run's view state, folded from its event stream. Pure: the same reducer serves live runs,
// reconnects, and finished runs (a finished run is its replayed event log).
import { ENDED, LIVE_ONLY, TERMINAL } from "../api/events";
import type { KeptPassage, RunDetail, RunEvent, RunStatus, Stage } from "../api/types";

/** The prototype's nine phases, in display order. The initial search runs inside `plan`. */
export const PHASES = [
  "plan",
  "search",
  "fetch",
  "load",
  "chunk",
  "prefilter",
  "score",
  "select",
  "write",
] as const satisfies readonly Stage[];
export type PhaseId = (typeof PHASES)[number];

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
};

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
  /** Keyed by URL (web) or path (file). */
  sources: Record<string, SourceView>;
  passages: ScoredQuery[];
  report: string;
  tokensIn: number;
  tokensOut: number;
  cost: number;
};

export function initialRunView(runId: string): RunView {
  const phases = {} as Record<PhaseId, Phase>;
  for (const id of PHASES) phases[id] = { state: "pending", counters: {} };
  return {
    runId,
    lastSeq: 0,
    status: "queued",
    phases,
    subQueries: [],
    sources: {},
    passages: [],
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
  return { ...state, phases };
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
    case "stage.started":
      return withPhase(state, event.stage, {
        state: "running",
        device: event.data.device ?? undefined,
        waitReason: undefined,
      });
    case "stage.progress": {
      const { done, total, failed } = event.data;
      return withPhase(state, event.stage, { counters: { done, total, failed } });
    }
    case "stage.done": {
      const d = event.data;
      const usage = d.usage ?? { input_tokens: 0, output_tokens: 0, cost: 0 };
      const phase = isPhase(event.stage) ? state.phases[event.stage] : undefined;
      let next = withPhase(state, event.stage, {
        state: d.copied_from ? "reused" : "done",
        copiedFrom: d.copied_from ?? undefined,
        skipped: d.skipped ?? false,
        counters: { ...phase?.counters, count: d.count },
      });
      if (event.stage === "search" || event.stage === "plan") {
        next = { ...next, subQueries: next.subQueries.map((q) => ({ ...q, done: true })) };
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
    case "plan.ready":
      return {
        ...state,
        subQueries: event.data.queries.map((q) => ({
          id: q.id,
          text: q.text,
          results: 0,
          done: false,
        })),
      };
    case "hit.found": {
      const { url, title, query_ids } = event.data;
      const subQueries = state.subQueries.map((q) =>
        query_ids.includes(q.id) ? { ...q, results: q.results + 1 } : q,
      );
      const known = state.sources[url];
      return withSource({ ...state, subQueries }, url, known ? {} : { title, uri: url });
    }
    case "page.fetched": {
      const d = event.data;
      return withSource(state, d.url, {
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

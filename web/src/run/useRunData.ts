// What the Live and Report screens need beyond the run's own events: its summary, the
// artifacts of finished stages, rejected passages on demand, and for a fork the data of the
// runs it copied stages from (a fork's log has their `stage.done` events, not their hits,
// pages, or passages).
import { useCallback, useEffect, useMemo, useState } from "react";
import { RunEvents } from "../api/events";
import type { Chunk, Context, Page, Report, Score } from "../api/generated";
import type { RunDetail } from "../api/types";
import { useServices } from "../app/context";
import {
  initialRunView,
  PHASES,
  type PhaseId,
  type RunView,
  runReducer,
  type SourceView,
} from "./reducer";
import { type PassageItem, parseJsonl, rejectedPassages } from "./scores";

export type FileRow = { sourceId: string; title: string; uri: string; size: number };

export type RunData = {
  detail: RunDetail | null;
  /** The run's view with the data of reused phases taken from the runs that ran them. */
  view: RunView | null;
  files: FileRow[];
  context: Context | null;
  report: Report | null;
  /** Null until requested with `showRejected` and loaded. */
  rejected: PassageItem[] | null;
  showRejected(): void;
};

export const ran = (view: RunView, phase: PhaseId) =>
  view.phases[phase].state === "done" || view.phases[phase].state === "reused";

const copiedFrom = (view: RunView) =>
  PHASES.map((id) => view.phases[id]).find((p) => p.state === "reused")?.copiedFrom;

/** The views of the runs a fork copied from, following `copied_from` to the first full run. */
function useAncestors(view: RunView | null): RunView[] {
  const { api, Socket } = useServices();
  const [views, setViews] = useState<Record<string, RunView>>({});
  const [chain, setChain] = useState<string[]>([]);
  const first = view ? copiedFrom(view) : undefined;

  useEffect(() => setChain(first ? [first] : []), [first]);
  const last = chain.at(-1);
  const next = last && views[last] ? copiedFrom(views[last]) : undefined;
  useEffect(() => {
    if (next && !chain.includes(next)) setChain((c) => [...c, next]);
  }, [next, chain]);

  useEffect(() => {
    if (!last) return;
    let state = initialRunView(last);
    const stream = new RunEvents(
      last,
      api,
      (update) => {
        if (update.kind !== "event") return;
        state = runReducer(state, update.event);
        setViews((v) => ({ ...v, [last]: state }));
      },
      Socket,
    );
    stream.start();
    return () => stream.close();
  }, [last, api, Socket]);

  return chain.map((id) => views[id]).filter(Boolean);
}

/** The view where `phase` ran: the run itself, or the nearest ancestor that did not copy it. */
function ranIn(views: RunView[], phase: PhaseId): RunView {
  return views.find((v) => v.phases[phase].state !== "reused") ?? views[views.length - 1];
}

export function withAncestors(view: RunView, ancestors: RunView[]): RunView {
  if (!ancestors.length) return view;
  const all = [view, ...ancestors];
  const searched = ranIn(all, "search");
  const fetched = ranIn(all, "fetch");
  const scored = ranIn(all, "score");
  const cached = fetched !== view;
  const sources: Record<string, SourceView> = {};
  for (const [key, s] of Object.entries({ ...searched.sources, ...fetched.sources })) {
    sources[key] = { ...s, cached: cached && s.state === "fetched", kept: 0 };
  }
  const bySourceId = new Map(Object.entries(sources).map(([k, s]) => [s.sourceId, k]));
  for (const q of scored.passages) {
    for (const p of q.items) {
      const key = bySourceId.get(p.source_id);
      if (key) sources[key] = { ...sources[key], kept: sources[key].kept + 1 };
    }
  }
  const reusedSearch = view.phases.search.state === "reused";
  return {
    ...view,
    subQueries: reusedSearch ? searched.subQueries : view.subQueries,
    sources,
    passages: scored.passages,
  };
}

const bytes = (text: string) => new TextEncoder().encode(text).length;

/** Fetches `name` once `ready` holds; null until then. */
function useArtifact<T>(
  runId: string | null,
  name: string,
  ready: boolean,
  parse: (text: string) => T,
): T | null {
  const { api } = useServices();
  const [value, setValue] = useState<{ runId: string; value: T } | null>(null);
  useEffect(() => {
    if (!runId || !ready) return;
    let live = true;
    api.getArtifact(runId, name).then(
      (text) => live && setValue({ runId, value: parse(text) }),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [api, runId, name, ready, parse]);
  return value && value.runId === runId ? value.value : null;
}

const parseFiles = (text: string): FileRow[] =>
  parseJsonl<Page>(text).map((p) => ({
    sourceId: p.source.source_id,
    title: p.source.title,
    uri: p.source.uri,
    size: bytes(p.text),
  }));
const parseContext = (text: string) => JSON.parse(text) as Context;
const parseReport = (text: string) => JSON.parse(text) as Report;
const parseScores = (text: string) => parseJsonl<Score>(text);
const parseChunks = (text: string) => parseJsonl<Chunk>(text);

export function useRunData(runId: string | null, own: RunView | null): RunData {
  const { api } = useServices();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [wantRejected, setWantRejected] = useState(false);

  useEffect(() => {
    setDetail(null);
    setWantRejected(false);
    if (!runId) return;
    let live = true;
    api.getRun(runId).then(
      (d) => live && setDetail(d),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [api, runId]);

  const ancestors = useAncestors(own);
  const view = useMemo(() => own && withAncestors(own, ancestors), [own, ancestors]);

  const loaded = !!own && ran(own, "load") && !own.phases.load.skipped;
  const files = useArtifact(runId, "files.jsonl", loaded, parseFiles);
  const context = useArtifact(runId, "context.json", !!own && ran(own, "select"), parseContext);
  const report = useArtifact(runId, "report.json", !!own && ran(own, "write"), parseReport);
  const scoreDone = wantRejected && !!own && ran(own, "score");
  const scores = useArtifact(runId, "scores.jsonl", scoreDone, parseScores);
  const chunks = useArtifact(runId, "chunks.jsonl", scoreDone, parseChunks);

  const rejected = useMemo(() => {
    if (!view || !scores || !chunks) return null;
    const thresholds = Object.fromEntries(view.passages.map((q) => [q.queryId, q.threshold]));
    const sources: Record<string, { title: string; uri: string }> = Object.fromEntries(
      Object.values(view.sources).map((s) => [s.sourceId, s]),
    );
    for (const f of files ?? []) sources[f.sourceId] = { title: f.title, uri: f.uri };
    return rejectedPassages(scores, chunks, thresholds, sources);
  }, [view, scores, chunks, files]);

  const showRejected = useCallback(() => setWantRejected(true), []);
  return { detail, view, files: files ?? [], context, report, rejected, showRejected };
}

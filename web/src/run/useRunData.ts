// What the Live and Report screens need beyond the run's own events: its summary, the
// artifacts of finished stages, the passages that were not kept on demand, and for a fork the data of the
// runs it copied stages from (a fork's log has their `stage.done` events, not their hits,
// pages, or passages).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { RunEvents } from "../api/events";
import type { Chunk, Context, Page, Report, Score, SelectSkip } from "../api/generated";
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
import { notKeptPassages, type PassageItem, parseJsonl } from "./scores";

export type FileRow = { sourceId: string; title: string; uri: string; size: number };

export type RunData = {
  detail: RunDetail | null;
  /** The server does not know the run. */
  notFound: boolean;
  /** The run's view with the data of reused phases taken from the runs that ran them. */
  view: RunView | null;
  files: FileRow[];
  context: Context | null;
  report: Report | null;
  /** Kept passages select did not take; null until select is done, or when the run has none. */
  skips: SelectSkip[] | null;
  /** Null until requested with `loadNotKept` and loaded. */
  notKept: PassageItem[] | null;
  loadNotKept(): void;
};

export const ran = (view: RunView, phase: PhaseId) =>
  view.phases[phase].state === "done" || view.phases[phase].state === "reused";

/** The runs that executed the view's reused phases: each copied `stage.done` names one. */
const sourceIds = (view: RunView | null): string[] => {
  if (!view) return [];
  const ids = PHASES.map((id) => view.phases[id])
    .filter((p) => p.state === "reused" && p.copiedFrom)
    .map((p) => p.copiedFrom as string);
  return [...new Set(ids)].sort();
};

/** The views of the runs a fork copied stages from, one stream each, kept until it ends. */
function useSources(view: RunView | null): Record<string, RunView> {
  const { api, Socket } = useServices();
  const [views, setViews] = useState<Record<string, RunView>>({});
  const streams = useRef(new Map<string, RunEvents>());
  const key = sourceIds(view).join(",");

  useEffect(() => {
    const ids = new Set(key ? key.split(",") : []);
    for (const [id, stream] of streams.current) {
      if (ids.has(id)) continue;
      stream.close();
      streams.current.delete(id);
    }
    for (const id of ids) {
      if (streams.current.has(id)) continue;
      let state = initialRunView(id);
      const stream = new RunEvents(
        id,
        api,
        (update) => {
          if (update.kind !== "event") return;
          state = runReducer(state, update.event);
          setViews((v) => ({ ...v, [id]: state }));
        },
        Socket,
      );
      streams.current.set(id, stream);
      stream.start();
    }
  }, [key, api, Socket]);

  useEffect(() => {
    const open = streams.current;
    return () => {
      for (const stream of open.values()) stream.close();
      open.clear();
    };
  }, []);

  return views;
}

/** The view where `phase` ran: the run named by its `copied_from`, else the run itself. */
function ranIn(view: RunView, sources: Record<string, RunView>, phase: PhaseId): RunView {
  const { state, copiedFrom } = view.phases[phase];
  return (state === "reused" && copiedFrom && sources[copiedFrom]) || view;
}

export function withAncestors(view: RunView, sources: Record<string, RunView>): RunView {
  if (!sourceIds(view).length) return view;
  const searched = ranIn(view, sources, "search");
  const fetched = ranIn(view, sources, "fetch");
  const scored = ranIn(view, sources, "score");
  const cached = fetched !== view;
  const merged: Record<string, SourceView> = {};
  for (const [key, s] of Object.entries({ ...searched.sources, ...fetched.sources })) {
    merged[key] = { ...s, cached: cached && s.state === "fetched", kept: 0 };
  }
  const bySourceId = new Map(Object.entries(merged).map(([k, s]) => [s.sourceId, k]));
  for (const q of scored.passages) {
    for (const p of q.items) {
      const key = bySourceId.get(p.source_id);
      if (key) merged[key] = { ...merged[key], kept: merged[key].kept + 1 };
    }
  }
  const reusedSearch = view.phases.search.state === "reused";
  return {
    ...view,
    subQueries: reusedSearch ? searched.subQueries : view.subQueries,
    sources: merged,
    passages: scored.passages,
  };
}

const bytes = (text: string) => new TextEncoder().encode(text).length;

/** Fetches `name` once `ready` holds; null until then, and null when it does not exist. */
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
const parseSkips = (text: string) => parseJsonl<SelectSkip>(text);

export function useRunData(runId: string | null, own: RunView | null): RunData {
  const { api } = useServices();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [wantNotKept, setWantNotKept] = useState(false);

  useEffect(() => {
    setDetail(null);
    setNotFound(false);
    setWantNotKept(false);
    if (!runId) return;
    let live = true;
    api.getRun(runId).then(
      (d) => live && setDetail(d),
      (error) => live && error instanceof ApiError && error.status === 404 && setNotFound(true),
    );
    return () => {
      live = false;
    };
  }, [api, runId]);

  const sources = useSources(own);
  const view = useMemo(() => own && withAncestors(own, sources), [own, sources]);

  const loaded = !!own && ran(own, "load") && !own.phases.load.skipped;
  const files = useArtifact(runId, "files.jsonl", loaded, parseFiles);
  const selected = !!own && ran(own, "select");
  const context = useArtifact(runId, "context.json", selected, parseContext);
  const skips = useArtifact(runId, "select.jsonl", selected, parseSkips);
  const report = useArtifact(runId, "report.json", !!own && ran(own, "write"), parseReport);
  const scoreDone = wantNotKept && !!own && ran(own, "score");
  const scores = useArtifact(runId, "scores.jsonl", scoreDone, parseScores);
  const chunks = useArtifact(runId, "chunks.jsonl", scoreDone, parseChunks);

  const notKept = useMemo(() => {
    if (!view || !scores || !chunks) return null;
    const thresholds = Object.fromEntries(view.passages.map((q) => [q.queryId, q.threshold]));
    const sources: Record<string, { title: string; uri: string }> = Object.fromEntries(
      Object.values(view.sources).map((s) => [s.sourceId, s]),
    );
    for (const f of files ?? []) sources[f.sourceId] = { title: f.title, uri: f.uri };
    return notKeptPassages(scores, chunks, thresholds, sources);
  }, [view, scores, chunks, files]);

  const loadNotKept = useCallback(() => setWantNotKept(true), []);
  return {
    detail,
    notFound,
    view,
    files: files ?? [],
    context,
    report,
    skips,
    notKept,
    loadNotKept,
  };
}

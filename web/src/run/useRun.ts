// Follows one run: its event stream and the server's summaries folded by the reducer, plus the
// connection state.
import { useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { type Conn, RunEvents } from "../api/events";
import type { RunEvent } from "../api/types";
import { ApiContext, type Services } from "../app/context";
import {
  applySummary,
  initialRunView,
  isEnded,
  type RunEnd,
  type RunView,
  runReducer,
} from "./reducer";

type Action = { reset: string } | { event: RunEvent } | { summary: RunEnd };

function reduce(state: RunView, action: Action): RunView {
  if ("reset" in action) return initialRunView(action.reset);
  if ("summary" in action) return applySummary(state, action.summary);
  const next = runReducer(state, action.event);
  // A summary can arrive before the replayed log, whose events cannot reopen an ended run.
  const open = next.status === "running" || next.status === "queued";
  return isEnded(state.status) && open ? { ...next, status: state.status } : next;
}

const IDLE: Conn = { state: "closed", attempt: 0, replayed: 0, notFound: false };

export type LiveRun = {
  view: RunView | null;
  conn: Conn;
  /** Applies how the run ended, as a cancel's 409 answer tells it. */
  end(summary: RunEnd): void;
  /** Reads the run summary once and applies it; a 404 shows the run as not found. */
  refresh(): void;
};

/** `services` overrides the ApiContext, for the App that provides it. */
export function useRun(runId: string | null, services?: Services): LiveRun {
  const provided = useContext(ApiContext);
  const resolved = services ?? provided;
  if (!resolved) throw new Error("ApiContext is not provided");
  const { api, Socket } = resolved;
  const [view, dispatch] = useReducer(reduce, initialRunView(runId ?? ""));
  const [conn, setConn] = useState<Conn>(IDLE);
  const stream = useRef<RunEvents | null>(null);

  useEffect(() => {
    if (!runId) return;
    dispatch({ reset: runId });
    const events = new RunEvents(
      runId,
      api,
      (update) => {
        if (update.kind === "event") dispatch({ event: update.event });
        else if (update.kind === "summary") dispatch({ summary: update.detail });
        else setConn(update.conn);
      },
      Socket,
    );
    stream.current = events;
    events.start();
    return () => {
      stream.current = null;
      events.close();
      setConn(IDLE);
    };
  }, [runId, api, Socket]);

  const end = useCallback((summary: RunEnd) => dispatch({ summary }), []);
  const refresh = useCallback(() => {
    if (!runId) return;
    api.getRun(runId).then(
      (detail) => dispatch({ summary: detail }),
      (error) => {
        if (!(error instanceof ApiError && error.status === 404)) return;
        stream.current?.close();
        setConn({ ...IDLE, notFound: true });
      },
    );
  }, [runId, api]);

  const current = runId && view.runId === runId ? view : null;
  return useMemo(() => ({ view: current, conn, end, refresh }), [current, conn, end, refresh]);
}

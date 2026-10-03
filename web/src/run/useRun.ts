// Follows one run: its event stream folded by the reducer, plus the connection state.
import { useContext, useEffect, useReducer, useState } from "react";
import { type Conn, RunEvents } from "../api/events";
import type { RunEvent } from "../api/types";
import { ApiContext, type Services } from "../app/context";
import { initialRunView, type RunView, runReducer } from "./reducer";

type Action = { reset: string } | { event: RunEvent } | { interrupted: true };

function reduce(state: RunView, action: Action): RunView {
  if ("reset" in action) return initialRunView(action.reset);
  if ("interrupted" in action) return { ...state, status: "interrupted" };
  const next = runReducer(state, action.event);
  // The summary can arrive before the replayed log, whose events cannot undo the interruption.
  const open = next.status === "running" || next.status === "queued";
  return state.status === "interrupted" && open ? { ...next, status: "interrupted" } : next;
}

const IDLE: Conn = { state: "closed", attempt: 0, replayed: 0, notFound: false };

/** `services` overrides the ApiContext, for the App that provides it. */
export function useRun(
  runId: string | null,
  services?: Services,
): { view: RunView | null; conn: Conn } {
  const provided = useContext(ApiContext);
  const resolved = services ?? provided;
  if (!resolved) throw new Error("ApiContext is not provided");
  const { api, Socket } = resolved;
  const [view, dispatch] = useReducer(reduce, initialRunView(runId ?? ""));
  const [conn, setConn] = useState<Conn>(IDLE);

  useEffect(() => {
    if (!runId) return;
    dispatch({ reset: runId });
    let live = true;
    const stream = new RunEvents(
      runId,
      api,
      (update) => {
        if (update.kind === "event") dispatch({ event: update.event });
        else setConn(update.conn);
      },
      Socket,
    );
    stream.start();
    // The event log cannot say a run was interrupted; the run summary can.
    api.getRun(runId).then(
      (detail) => live && detail.status === "interrupted" && dispatch({ interrupted: true }),
      () => {},
    );
    return () => {
      live = false;
      stream.close();
      setConn(IDLE);
    };
  }, [runId, api, Socket]);

  return { view: runId && view.runId === runId ? view : null, conn };
}

// One run's event stream over WS /api/runs/{id}/events, reconnecting with `since` after a drop.
import { type ApiClient, ApiError } from "./client";
import type { RunDetail, RunEvent } from "./types";

export type ConnState =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "replaying"
  | "unavailable"
  | "closed";
export type Conn = { state: ConnState; attempt: number; replayed: number; notFound: boolean };
export type StreamUpdate =
  | { kind: "event"; event: RunEvent }
  | { kind: "conn"; conn: Conn }
  | { kind: "summary"; detail: RunDetail };

type Socket = {
  onopen: (() => void) | null;
  onmessage: ((message: { data: string }) => void) | null;
  onclose: ((close: { code: number }) => void) | null;
  close(): void;
};
export type SocketFactory = new (url: string) => Socket;

export const RECONNECT_MS = 2000;
export const MAX_RECONNECT_MS = 30000;
/** Reconnect attempts in a row whose socket never opened before the stream is "unavailable". */
const UNAVAILABLE_AFTER = 3;
const NORMAL = 1000;
const NOT_FOUND = 4404;
export const LIVE_ONLY = new Set(["run.queued", "report.delta", "report.snapshot"]);
export const TERMINAL = new Set(["run.done", "run.failed", "run.cancelled"]);
export const ENDED = new Set(["done", "failed", "cancelled", "interrupted"]);

export function eventsUrl(runId: string, since: number, at: Location = window.location): string {
  const scheme = at.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${at.host}/api/runs/${encodeURIComponent(runId)}/events?since=${since}`;
}

/** Wait before reconnect attempt `attempt` (1-based): 2, 4, 8, 16, then 30 seconds. */
export function reconnectDelay(attempt: number): number {
  return Math.min(RECONNECT_MS * 2 ** (attempt - 1), MAX_RECONNECT_MS);
}

export class RunEvents {
  private socket: Socket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private lastSeq = 0;
  private replayUntil = 0;
  private pendingReplay = 0;
  private ended = false;
  private stopped = false;
  private conn: Conn = { state: "connecting", attempt: 0, replayed: 0, notFound: false };

  constructor(
    private readonly runId: string,
    private readonly api: Pick<ApiClient, "getRun">,
    private readonly onUpdate: (update: StreamUpdate) => void,
    private readonly Socket: SocketFactory = WebSocket as unknown as SocketFactory,
  ) {}

  start() {
    this.report({ state: "connecting" });
    // Runs beside the first socket; a failure here only matters for a 404.
    this.summary().catch(() => {});
    this.open(0);
  }

  /** Stops for good: closes the socket and cancels a pending reconnect. */
  close() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  }

  private report(patch: Partial<Conn>) {
    this.conn = { ...this.conn, ...patch };
    this.onUpdate({ kind: "conn", conn: this.conn });
  }

  /** Reads the run summary and emits it; null when the stream must not go on. */
  private async summary(): Promise<RunDetail | null> {
    let detail: RunDetail;
    try {
      detail = await this.api.getRun(this.runId);
    } catch (error) {
      if (this.stopped) return null;
      if (error instanceof ApiError && error.status === 404) {
        this.close();
        this.report({ state: "closed", notFound: true });
      }
      // A 401 has already locked the app through the client; the next attempt follows sign-in.
      throw error;
    }
    if (this.stopped) return null;
    this.onUpdate({ kind: "summary", detail });
    return detail;
  }

  private open(since: number) {
    const socket = new this.Socket(eventsUrl(this.runId, since));
    this.socket = socket;
    socket.onopen = () => {
      const replayed = this.pendingReplay;
      this.pendingReplay = 0;
      if (replayed > 0) this.report({ state: "replaying", replayed, attempt: 0 });
      else this.report({ state: "connected", attempt: 0 });
    };
    socket.onmessage = (message) => this.receive(JSON.parse(message.data) as RunEvent);
    socket.onclose = ({ code }) => {
      if (this.socket !== socket || this.stopped) return;
      this.socket = null;
      if (code === NOT_FOUND) this.report({ state: "closed", notFound: true });
      else if (code === NORMAL || this.ended) this.report({ state: "closed" });
      else this.retry();
    };
  }

  private receive(event: RunEvent) {
    if (!LIVE_ONLY.has(event.type)) this.lastSeq = Math.max(this.lastSeq, event.seq);
    if (TERMINAL.has(event.type)) this.ended = true;
    this.onUpdate({ kind: "event", event });
    if (this.conn.state === "replaying" && event.seq >= this.replayUntil) {
      this.report({ state: "connected" });
    }
  }

  /** Schedules the next attempt. `attempt` only resets when a socket opens. */
  private retry() {
    const attempt = this.conn.attempt + 1;
    const unavailable = this.conn.state === "unavailable" || attempt > UNAVAILABLE_AFTER;
    this.report({ state: unavailable ? "unavailable" : "reconnecting", attempt });
    const wait = unavailable ? MAX_RECONNECT_MS : reconnectDelay(attempt);
    this.timer = setTimeout(() => void this.reconnect(), wait);
  }

  private async reconnect() {
    this.timer = null;
    let detail: RunDetail | null;
    try {
      detail = await this.summary();
    } catch {
      if (!this.stopped && !this.conn.notFound) this.retry();
      return;
    }
    if (!detail) return;
    const lastSeq = detail.last_seq ?? 0;
    const since = this.lastSeq;
    if (ENDED.has(detail.status) && (lastSeq <= since || this.conn.state === "unavailable")) {
      this.stopped = true;
      this.report({ state: "closed" });
      return;
    }
    this.pendingReplay = Math.max(lastSeq - since, 0);
    this.replayUntil = lastSeq;
    this.open(since);
  }
}

// One run's event stream over WS /api/runs/{id}/events, reconnecting with `since` after a drop.
import type { ApiClient } from "./client";
import type { RunEvent } from "./types";

export type ConnState = "connecting" | "connected" | "reconnecting" | "replaying" | "closed";
export type Conn = { state: ConnState; attempt: number; replayed: number; notFound: boolean };
export type StreamUpdate = { kind: "event"; event: RunEvent } | { kind: "conn"; conn: Conn };

type Socket = {
  onopen: (() => void) | null;
  onmessage: ((message: { data: string }) => void) | null;
  onclose: ((close: { code: number }) => void) | null;
  close(): void;
};
export type SocketFactory = new (url: string) => Socket;

export const RECONNECT_MS = 2000;
const NORMAL = 1000;
const NOT_FOUND = 4404;
const LIVE_ONLY = new Set(["run.queued", "report.delta", "report.snapshot"]);
const TERMINAL = new Set(["run.done", "run.failed", "run.cancelled"]);

export function eventsUrl(runId: string, since: number, at: Location = window.location): string {
  const scheme = at.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${at.host}/api/runs/${encodeURIComponent(runId)}/events?since=${since}`;
}

export class RunEvents {
  private socket: Socket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private lastSeq = 0;
  private replayUntil = 0;
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

  private open(since: number) {
    const socket = new this.Socket(eventsUrl(this.runId, since));
    this.socket = socket;
    socket.onopen = () => {
      if (this.conn.state !== "replaying") this.report({ state: "connected", attempt: 0 });
      else this.report({ attempt: 0 });
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

  private retry() {
    this.report({ state: "reconnecting", attempt: this.conn.attempt + 1 });
    this.timer = setTimeout(() => void this.reconnect(), RECONNECT_MS);
  }

  private async reconnect() {
    this.timer = null;
    let lastSeq: number;
    try {
      lastSeq = (await this.api.getRun(this.runId)).last_seq ?? 0;
    } catch {
      // A 401 has already locked the app through the client; keep trying until signed in.
      if (!this.stopped) this.retry();
      return;
    }
    if (this.stopped) return;
    const since = this.lastSeq;
    if (lastSeq > since) {
      this.replayUntil = lastSeq;
      this.report({ state: "replaying", replayed: lastSeq - since });
    }
    this.open(since);
  }
}

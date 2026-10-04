import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ev, stageDone } from "../test/events";
import { FakeWebSocket } from "../test/FakeWebSocket";
import { callsTo, fakeApi } from "../test/fakeApi";
import { ApiError } from "./client";
import { type Conn, RunEvents, type SocketFactory, type StreamUpdate } from "./events";

const Socket = FakeWebSocket as unknown as SocketFactory;

type Summary = { last_seq?: number; status?: "running" | "done" | "failed" } | "missing";

/** `summary` answers every `getRun`; a function lets a test change it between attempts. */
function setup(lastSeq = 400, summary: () => Summary = () => ({})) {
  const api = fakeApi();
  api.getRun = vi.fn(async (id: string) => {
    const answer = summary();
    if (answer === "missing") throw new ApiError(404, "run_not_found", "gone");
    return {
      ...(await fakeApi().getRun(id)),
      last_seq: lastSeq,
      status: "running" as const,
      ...answer,
    };
  });
  const updates: StreamUpdate[] = [];
  const stream = new RunEvents("r_8c21", api, (u) => updates.push(u), Socket);
  const conns = () =>
    updates.filter((u) => u.kind === "conn").map((u) => (u as { conn: Conn }).conn);
  const seqs = () => updates.flatMap((u) => (u.kind === "event" ? [u.event.seq] : []));
  stream.start();
  const states = () => conns().map((c) => c.state);
  return { api, stream, conns, seqs, states, updates };
}

const since = (socket: FakeWebSocket) => new URL(socket.url).searchParams.get("since");

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.reset();
});
afterEach(() => vi.useRealTimers());

describe("RunEvents", () => {
  it("starts at since=0 and reconnects with the last applied seq after a drop", async () => {
    const { api, conns, seqs } = setup(400);
    const first = FakeWebSocket.last();
    expect(first.url).toMatch(/^ws:\/\/[^/]+\/api\/runs\/r_8c21\/events\?since=0$/);
    first.open();
    first.emit(stageDone(350, "fetch"), stageDone(351, "chunk"));
    first.emit(ev(351, "report.delta", { text: "x" }));
    first.serverClose(1006);
    expect(conns().at(-1)).toMatchObject({ state: "reconnecting", attempt: 1 });

    await vi.advanceTimersByTimeAsync(2000);
    expect(api.getRun).toHaveBeenCalledWith("r_8c21");
    const second = FakeWebSocket.last();
    expect(since(second)).toBe("351");
    expect(conns().at(-1)?.state).toBe("reconnecting");
    second.open();
    expect(conns().at(-1)).toMatchObject({ state: "replaying", replayed: 49, attempt: 0 });
    second.emit(stageDone(352, "prefilter"), stageDone(400, "score"));
    expect(conns().at(-1)).toMatchObject({ state: "connected", replayed: 49 });
    expect(seqs()).toEqual([350, 351, 351, 352, 400]);
  });

  it("emits the run summary at start", async () => {
    const { updates } = setup(0, () => ({ status: "failed" }));
    await vi.advanceTimersByTimeAsync(0);
    expect(updates.find((u) => u.kind === "summary")).toMatchObject({
      detail: { status: "failed" },
    });
  });

  it("backs off and becomes unavailable when the handshake keeps failing", async () => {
    const { states, conns } = setup();
    FakeWebSocket.last().serverClose(1006);
    for (const [attempt, wait] of [
      [1, 2000],
      [2, 4000],
      [3, 8000],
    ]) {
      expect(conns().at(-1)).toMatchObject({ state: "reconnecting", attempt });
      await vi.advanceTimersByTimeAsync(wait - 1);
      expect(FakeWebSocket.instances).toHaveLength(attempt);
      await vi.advanceTimersByTimeAsync(1);
      expect(FakeWebSocket.instances).toHaveLength(attempt + 1);
      FakeWebSocket.last().serverClose(1006);
    }
    expect(conns().at(-1)?.state).toBe("unavailable");
    expect(states()).not.toContain("replaying");
    await vi.advanceTimersByTimeAsync(30000);
    expect(FakeWebSocket.instances).toHaveLength(5);
  });

  it("returns to replaying when a socket opens after unavailable", async () => {
    const { conns, states } = setup(400);
    const sockets = FakeWebSocket.instances;
    sockets[0].open();
    sockets[0].emit(stageDone(351, "chunk"));
    sockets[0].serverClose(1006);
    for (const wait of [2000, 4000, 8000]) {
      await vi.advanceTimersByTimeAsync(wait);
      FakeWebSocket.last().serverClose(1006);
    }
    expect(conns().at(-1)?.state).toBe("unavailable");
    await vi.advanceTimersByTimeAsync(30000);
    expect(states().at(-1)).toBe("unavailable");
    FakeWebSocket.last().open();
    expect(conns().at(-1)).toMatchObject({ state: "replaying", replayed: 49 });
    FakeWebSocket.last().emit(stageDone(400, "score"));
    expect(conns().at(-1)?.state).toBe("connected");
  });

  it("stops when the run summary answers 404 before an attempt", async () => {
    let missing = false;
    const { conns } = setup(400, () => (missing ? "missing" : {}));
    await vi.advanceTimersByTimeAsync(0);
    missing = true;
    FakeWebSocket.last().serverClose(1006);
    await vi.advanceTimersByTimeAsync(60000);
    expect(conns().at(-1)).toMatchObject({ state: "closed", notFound: true });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("stops when the run ended while unavailable", async () => {
    let ended = false;
    const { conns } = setup(400, () => (ended ? { status: "done" } : {}));
    FakeWebSocket.last().serverClose(1006);
    for (const wait of [2000, 4000, 8000]) {
      await vi.advanceTimersByTimeAsync(wait);
      FakeWebSocket.last().serverClose(1006);
    }
    expect(conns().at(-1)?.state).toBe("unavailable");
    ended = true;
    await vi.advanceTimersByTimeAsync(30000);
    expect(conns().at(-1)?.state).toBe("closed");
    expect(FakeWebSocket.instances).toHaveLength(4);
    await vi.advanceTimersByTimeAsync(60000);
    expect(FakeWebSocket.instances).toHaveLength(4);
  });

  it("reconnects after 4408 (slow client)", async () => {
    setup();
    FakeWebSocket.last().open();
    FakeWebSocket.last().serverClose(4408);
    await vi.advanceTimersByTimeAsync(2000);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("does not reconnect after 1000 or a terminal event", async () => {
    const { conns } = setup();
    const socket = FakeWebSocket.last();
    socket.open();
    socket.emit(ev(9, "run.done", { until: null, totals: {} as never }));
    socket.serverClose(1006);
    await vi.advanceTimersByTimeAsync(4000);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(conns().at(-1)?.state).toBe("closed");

    FakeWebSocket.reset();
    setup();
    FakeWebSocket.last().serverClose(1000);
    await vi.advanceTimersByTimeAsync(4000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("reports notFound on 4404 without reconnecting", async () => {
    const { api, conns } = setup();
    FakeWebSocket.last().serverClose(4404);
    await vi.advanceTimersByTimeAsync(4000);
    expect(conns().at(-1)).toMatchObject({ state: "closed", notFound: true });
    expect(callsTo(api, "getRun")).toHaveLength(0);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("closes the socket and cancels a pending reconnect on close()", async () => {
    const { stream } = setup();
    FakeWebSocket.last().serverClose(1006);
    stream.close();
    await vi.advanceTimersByTimeAsync(4000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});

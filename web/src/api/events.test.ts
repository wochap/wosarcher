import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ev, stageDone } from "../test/events";
import { FakeWebSocket } from "../test/FakeWebSocket";
import { callsTo, fakeApi } from "../test/fakeApi";
import { type Conn, RunEvents, type SocketFactory, type StreamUpdate } from "./events";

const Socket = FakeWebSocket as unknown as SocketFactory;

function setup(lastSeq = 400) {
  const api = fakeApi();
  api.getRun = vi.fn(async (id: string) => ({
    ...(await fakeApi().getRun(id)),
    last_seq: lastSeq,
  }));
  const updates: StreamUpdate[] = [];
  const stream = new RunEvents("r_8c21", api, (u) => updates.push(u), Socket);
  const conns = () =>
    updates.filter((u) => u.kind === "conn").map((u) => (u as { conn: Conn }).conn);
  const seqs = () => updates.flatMap((u) => (u.kind === "event" ? [u.event.seq] : []));
  stream.start();
  return { api, stream, conns, seqs };
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
    expect(conns().at(-1)).toMatchObject({ state: "replaying", replayed: 49 });
    second.open();
    second.emit(stageDone(352, "prefilter"), stageDone(400, "score"));
    expect(conns().at(-1)).toMatchObject({ state: "connected", replayed: 49 });
    expect(seqs()).toEqual([350, 351, 351, 352, 400]);
  });

  it("counts attempts while reconnects keep failing", async () => {
    const { conns } = setup();
    FakeWebSocket.last().open();
    FakeWebSocket.last().serverClose(1006);
    expect(conns().at(-1)?.attempt).toBe(1);
    await vi.advanceTimersByTimeAsync(2000);
    FakeWebSocket.last().serverClose(1006);
    expect(conns().at(-1)?.attempt).toBe(2);
    await vi.advanceTimersByTimeAsync(2000);
    FakeWebSocket.last().serverClose(1006);
    expect(conns().at(-1)?.attempt).toBe(3);
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

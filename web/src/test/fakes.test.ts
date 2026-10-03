import { describe, expect, it } from "vitest";
import { FakeWebSocket } from "./FakeWebSocket";
import { callsTo, fakeApi } from "./fakeApi";

describe("fakeApi", () => {
  it("serves fixture data and records calls", async () => {
    const api = fakeApi();
    const runs = await api.listRuns();
    expect(runs.length).toBeGreaterThan(0);
    await api.deleteRun(runs[0].run_id);
    expect(callsTo(api, "deleteRun")).toEqual([[runs[0].run_id]]);
    expect((await api.listRuns()).length).toBe(runs.length - 1);
  });

  it("answers scripted logins in order, then succeeds", async () => {
    const api = fakeApi({ logins: [{ kind: "wrong", attemptsLeft: 3 }] });
    expect((await api.login("a")).kind).toBe("wrong");
    expect((await api.login("b")).kind).toBe("ok");
  });
});

describe("FakeWebSocket", () => {
  it("delivers events and closes", () => {
    FakeWebSocket.reset();
    const socket = new FakeWebSocket("ws://x/api/runs/r1/events?since=0");
    const seen: string[] = [];
    let code = 0;
    socket.onmessage = (m) => seen.push(m.data);
    socket.onclose = (c) => {
      code = c.code;
    };
    socket.open();
    socket.emit({ type: "run.queued", seq: 0, run_id: "r1", ts: "", data: { position: 1 } });
    socket.serverClose(1000);
    expect(FakeWebSocket.last()).toBe(socket);
    expect(JSON.parse(seen[0]).type).toBe("run.queued");
    expect(code).toBe(1000);
  });
});

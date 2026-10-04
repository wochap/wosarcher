import { act, render } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { SocketFactory } from "../api/events";
import type { RunEvent } from "../api/types";
import { ApiContext } from "../app/context";
import { FakeWebSocket } from "../test/FakeWebSocket";
import { callsTo, type FakeApi, fakeApi } from "../test/fakeApi";
import { finished } from "../test/fixtures/finished";
import { FILE_PAGES, Log, RUN_ID, summary, upTo } from "../test/fixtures/sample";
import { REWRITE_ID, versions } from "../test/fixtures/versions";
import { useRun } from "./useRun";
import { type RunData, useRunData } from "./useRunData";

let data: RunData;

function Probe({ runId }: { runId: string }) {
  const { view } = useRun(runId);
  data = useRunData(runId, view);
  return null;
}

function mount(api: FakeApi, runId: string) {
  render(
    <ApiContext.Provider value={{ api, Socket: FakeWebSocket as unknown as SocketFactory }}>
      <Probe runId={runId} />
    </ApiContext.Provider>,
  );
}

const socketFor = (runId: string) =>
  FakeWebSocket.instances.find((s) => s.url.includes(`/runs/${runId}/`)) as FakeWebSocket;

async function play(runId: string, events: RunEvent[]) {
  await act(async () => {
    socketFor(runId).open();
    socketFor(runId).emit(...events);
  });
}

const artifactsRead = (api: FakeApi) => callsTo(api, "getArtifact").map((args) => args[1]);
const doneAt = (stage: string) => (e: RunEvent) => e.type === "stage.done" && e.stage === stage;

beforeEach(() => FakeWebSocket.reset());

describe("useRunData", () => {
  it("fetches each artifact only after its stage is done", async () => {
    const api = fakeApi(finished.data);
    const events = api.data.events[RUN_ID];
    mount(api, RUN_ID);
    await play(RUN_ID, upTo(events, doneAt("load")));
    expect(artifactsRead(api)).toEqual([]);
    expect(data.detail?.run_id).toBe(RUN_ID);

    const rest = events.slice(upTo(events, doneAt("load")).length);
    await act(async () => {
      socketFor(RUN_ID).emit(...upTo(rest, doneAt("select")));
    });
    expect(artifactsRead(api)).toEqual(["files.jsonl"]);
    const size = new TextEncoder().encode(FILE_PAGES[0].text).length;
    expect(data.files[0]).toMatchObject({ title: "bench-3060.md", size });
    expect(size).toBe(4403);

    await act(async () => {
      socketFor(RUN_ID).emit(...rest);
    });
    expect(artifactsRead(api)).toEqual([
      "files.jsonl",
      "context.json",
      "select.jsonl",
      "report.json",
    ]);
    expect(data.context?.passages).toHaveLength(14);
    expect(data.report?.cited).toContain(14);
    expect(data.skips?.map((s) => s.reason)).toEqual(["source_cap", "budget"]);
    expect(artifactsRead(api)).not.toContain("scores.jsonl");

    await act(async () => {
      data.loadNotKept();
    });
    expect(artifactsRead(api)).toContain("scores.jsonl");
    expect(artifactsRead(api)).toContain("chunks.jsonl");
    expect(data.notKept?.map((p) => p.display)).toContain(0.52);
    expect(data.notKept?.every((p) => !p.kept && p.threshold === 0.6)).toBe(true);
    expect(data.notKept?.find((p) => p.chunk_id === "c17")?.dropped).toBe("query_cap");
    expect(data.notKept?.some((p) => p.chunk_id === "c1")).toBe(false);
  });

  it("shows a fork's sources and passages from the run it copied them from", async () => {
    const api = fakeApi(versions.data);
    mount(api, REWRITE_ID);
    await play(REWRITE_ID, api.data.events[REWRITE_ID]);
    expect(data.view?.phases.fetch.state).toBe("reused");
    await play(RUN_ID, api.data.events[RUN_ID]);
    const sources = Object.values(data.view?.sources ?? {});
    expect(sources).toHaveLength(22);
    expect(sources.filter((s) => s.cached)).toHaveLength(19);
    expect(data.view?.subQueries).toHaveLength(5);
    expect(data.view?.passages.flatMap((q) => q.items)).toHaveLength(16);
  });

  it("follows each run named by copied_from in a two-hop lineage", async () => {
    // B forks A from score; C forks B from write. C's copied events name the run that ran each stage.
    const [A, B, C] = [RUN_ID, "r_b", "r_c"];
    const early = ["plan", "search", "load", "fetch", "chunk", "prefilter"];
    const scoring = new Set(["score", "select"]);
    const a = fakeApi(finished.data).data.events[A];
    const started = (log: Log, parent: string, version: number) =>
      log.add("run.started", {
        query: "q",
        profile: "p",
        parent_run_id: parent,
        until: null,
        version,
      });
    const b = started(new Log(B), A, 2);
    for (const stage of early) b.done(stage, 1, { copied_from: A });
    for (const e of a) if (e.stage && scoring.has(e.stage)) b.add(e.type, e.data as never, e.stage);
    b.add("run.done", { until: null, totals: {} as never });
    const c = started(new Log(C), B, 3);
    for (const stage of early) c.done(stage, 1, { copied_from: A });
    for (const stage of scoring) c.done(stage, 1, { copied_from: B });
    const api = fakeApi({
      ...finished.data,
      runs: [summary({ run_id: C }), summary({ run_id: B }), summary()],
      events: { [A]: a, [B]: b.events, [C]: c.events },
    });
    mount(api, C);
    await play(C, c.events);
    await play(B, b.events);
    expect(socketFor(A).closedByClient).toBe(false);
    await play(A, a);
    expect(socketFor(B).closedByClient).toBe(false);
    const sources = Object.values(data.view?.sources ?? {});
    expect(sources).toHaveLength(22);
    expect(sources.filter((s) => s.cached)).toHaveLength(19);
    expect(data.view?.passages.flatMap((q) => q.items)).toHaveLength(16);
    expect(FakeWebSocket.instances.filter((s) => s.url.includes(`/runs/${A}/`))).toHaveLength(1);
  });
});

import { act, render } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { SocketFactory } from "../api/events";
import type { RunEvent } from "../api/types";
import { ApiContext } from "../app/context";
import { FakeWebSocket } from "../test/FakeWebSocket";
import { callsTo, type FakeApi, fakeApi } from "../test/fakeApi";
import { finished } from "../test/fixtures/finished";
import { FILE_PAGES, RUN_ID, upTo } from "../test/fixtures/sample";
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
    expect(artifactsRead(api)).toEqual(["files.jsonl", "context.json", "report.json"]);
    expect(data.context?.passages).toHaveLength(14);
    expect(data.report?.cited).toContain(14);

    await act(async () => {
      data.showRejected();
    });
    expect(artifactsRead(api)).toContain("scores.jsonl");
    expect(data.rejected?.map((p) => p.display)).toContain(0.52);
    expect(data.rejected?.every((p) => !p.kept && p.threshold === 0.6)).toBe(true);
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
    expect(data.view?.passages.flatMap((q) => q.items)).toHaveLength(14);
  });
});

import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import { ev, stageDone, usage } from "../test/events";
import { initialRunView, type RunView, runReducer } from "./reducer";

const fold = (events: RunEvent[], from: RunView = initialRunView("r1")) =>
  events.reduce(runReducer, from);

const started = ev(1, "run.started", {
  query: "q",
  profile: "low-vram",
  parent_run_id: null,
  version: 1,
  until: null,
});

describe("runReducer", () => {
  it("ignores a logged event whose seq was already applied", () => {
    const state = fold([started, ev(2, "plan.ready", { queries: [{ id: "q1", text: "a" }] })]);
    expect(runReducer(state, ev(2, "plan.ready", { queries: [] }))).toBe(state);
    expect(state.lastSeq).toBe(2);
  });

  it("applies live-only events without moving lastSeq", () => {
    let state = fold([started]);
    state = runReducer(state, ev(1, "run.queued", { position: 2 }));
    expect(state.queuePosition).toBe(2);
    state = runReducer(state, ev(1, "report.delta", { text: "Hello" }));
    state = runReducer(state, ev(1, "report.delta", { text: " there" }));
    expect(state.report).toBe("Hello there");
    state = runReducer(state, ev(1, "report.snapshot", { text: "Hello world" }));
    expect(state.report).toBe("Hello world");
    expect(state.lastSeq).toBe(1);
  });

  it("moves a phase through waiting, running, and done with its device", () => {
    let state = fold([started]);
    state = runReducer(
      state,
      ev(2, "resource.waiting", { device: "gpu0", released_stage: "prefilter" }, "score"),
    );
    expect(state.phases.score).toMatchObject({
      state: "waiting",
      waitReason: "prefilter unloading",
    });
    state = runReducer(
      state,
      ev(3, "stage.started", { device: "gpu0", provider: "rerank" }, "score"),
    );
    expect(state.phases.score).toMatchObject({ state: "running", device: "gpu0" });
    state = runReducer(state, ev(4, "stage.progress", { done: 3, total: 9, failed: 1 }, "score"));
    expect(state.phases.score.counters).toEqual({ done: 3, total: 9, failed: 1 });
    state = runReducer(state, stageDone(5, "score"));
    expect(state.phases.score.state).toBe("done");
  });

  it("marks a copied stage reused and a skipped stage done and skipped", () => {
    const state = fold([
      started,
      stageDone(2, "search", { copied_from: "r0" }),
      stageDone(3, "prefilter", { skipped: true }),
    ]);
    expect(state.phases.search).toMatchObject({ state: "reused", copiedFrom: "r0" });
    expect(state.phases.prefilter).toMatchObject({ state: "done", skipped: true });
  });

  it("keeps the failed stage and its error", () => {
    const state = fold([
      started,
      ev(2, "stage.started", { device: "gpu0", provider: "rerank" }, "score"),
      ev(3, "stage.failed", { error: "CUDA out of memory", next: "" }, "score"),
      ev(4, "run.failed", { stage: "score", error: "CUDA out of memory" }),
    ]);
    expect(state.status).toBe("failed");
    expect(state.phases.score).toMatchObject({ state: "failed", error: "CUDA out of memory" });
    expect(state.failure).toEqual({ stage: "score", error: "CUDA out of memory" });
  });

  it("marks the running phase cancelled on cancel", () => {
    const state = fold([
      started,
      ev(2, "stage.started", { device: null, provider: "httpx" }, "fetch"),
      ev(3, "run.cancelled", { stage: "fetch" }),
    ]);
    expect(state.status).toBe("cancelled");
    expect(state.phases.fetch.state).toBe("cancelled");
  });

  it("sums tokens and cost over stage.done", () => {
    const state = fold([
      started,
      stageDone(2, "plan", { usage: usage(1200, 160, 0.001) }),
      stageDone(3, "score", { usage: usage(38400, 0, 0.002) }),
    ]);
    expect(state.tokensIn).toBe(39600);
    expect(state.tokensOut).toBe(160);
    expect(state.cost).toBeCloseTo(0.003);
  });

  it("tracks sources found, fetched, failed, and kept counts", () => {
    const state = fold([
      started,
      ev(2, "plan.ready", { queries: [{ id: "q1", text: "a" }] }),
      ev(3, "hit.found", { url: "https://a", title: "A", query_ids: ["q1"] }),
      ev(4, "hit.found", { url: "https://b", title: "B", query_ids: ["q1"] }),
      ev(5, "hit.found", { url: "https://c", title: "C", query_ids: [] }),
      ev(
        6,
        "page.fetched",
        { url: "https://a", source_id: "s1", title: "A", chars: 9, cached: false },
        "fetch",
      ),
      ev(7, "page.failed", { url: "https://b", reason: "403 Forbidden" }, "fetch"),
      ev(8, "passages.scored", {
        query_id: "q1",
        scorer: "rerank",
        scored: 4,
        kept: 2,
        threshold_display: 0.6,
        passages: [
          {
            chunk_id: "c1",
            source_id: "s1",
            title: "A",
            uri: "https://a",
            text: "x",
            display: 0.9,
            heading_path: [],
          },
          {
            chunk_id: "c2",
            source_id: "s1",
            title: "A",
            uri: "https://a",
            text: "y",
            display: 0.7,
            heading_path: [],
          },
        ],
      }),
    ]);
    expect(state.subQueries[0].results).toBe(2);
    expect(state.sources["https://a"]).toMatchObject({ state: "fetched", sourceId: "s1", kept: 2 });
    expect(state.sources["https://b"]).toMatchObject({ state: "failed", reason: "403 Forbidden" });
    expect(state.sources["https://c"].state).toBe("found");
    expect(state.passages[0]).toMatchObject({ scorer: "rerank", threshold: 0.6, kept: 2 });
  });
});

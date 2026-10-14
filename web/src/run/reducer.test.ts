import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import { ev, stageDone, usage } from "../test/events";
import { roundsLog, roundTwoFetching } from "../test/rounds";
import { isFallback } from "./providers";
import { applySummary, initialRunView, type RunView, runReducer } from "./reducer";
import { fmtDuration, stageTime, timeBar, timeRow } from "./stageTimes";

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
    state = runReducer(state, ev(1, "run.queued", { position: 2, limit: 1 }));
    expect(state.queued?.position).toBe(2);
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

  it("keeps the configured provider and the one that ran (prefilter fallback)", () => {
    const warning = "embeddings prefilter failed, used bm25: connection refused";
    const state = fold([
      started,
      ev(
        2,
        "stage.started",
        { device: "gpu0", provider: "embeddings:bge-small-en-v1.5" },
        "prefilter",
      ),
      stageDone(3, "prefilter", {
        provider: "bm25",
        warnings: [warning],
        passthrough: ["q4", "q5"],
      }),
    ]);
    const phase = state.phases.prefilter;
    expect(phase).toMatchObject({
      configuredProvider: "embeddings:bge-small-en-v1.5",
      provider: "bm25",
      warnings: [warning],
    });
    expect(isFallback(phase.configuredProvider, phase.provider)).toBe(true);
    expect(state.passthrough).toEqual(["q4", "q5"]);
  });

  it("sums the hits filtered by domain over plan and search", () => {
    const state = fold([
      started,
      stageDone(2, "plan", { filtered: 3 }),
      stageDone(3, "search", { filtered: 9 }),
      stageDone(4, "fetch", {}),
    ]);
    expect(state.filtered).toBe(12);
  });

  it("is not a fallback when the same method ran without its model", () => {
    const state = fold([
      started,
      ev(2, "stage.started", { device: "gpu0", provider: "rerank:bge-reranker" }, "score"),
      stageDone(3, "score", { provider: "rerank" }),
    ]);
    const phase = state.phases.score;
    expect(isFallback(phase.configuredProvider, phase.provider)).toBe(false);
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

  it("counts a topic searched in Search toward Search, not Plan", () => {
    const state = fold([
      started,
      ev(2, "stage.started", { device: null, provider: "x" }, "plan"),
      ev(3, "plan.ready", {
        queries: [
          { id: "q0", text: "topic" },
          { id: "q1", text: "a" },
        ],
      }),
      stageDone(4, "plan"),
      ev(5, "stage.started", { device: null, provider: "x" }, "search"),
      ev(6, "hit.found", { url: "https://a", title: "A", query_ids: ["q0"] }, "search"),
      ev(7, "hit.found", { url: "https://b", title: "B", query_ids: ["q0", "q1"] }, "search"),
    ]);
    expect(state.phases.search.counters.hits).toBe(2);
    expect(state.phases.plan.counters.hits).toBeUndefined();
    expect(state.subQueries.map((q) => [q.id, q.results])).toEqual([
      ["q0", 2],
      ["q1", 1],
    ]);
    expect(state.rounds[0].queries.map((q) => q.id)).toEqual(["q0", "q1"]);
  });

  it("counts initial-search hits toward Plan and the topic row", () => {
    const state = fold([
      started,
      ev(2, "stage.started", { device: null, provider: "x" }, "plan"),
      ev(3, "hit.found", { url: "https://a", title: "A", query_ids: ["q0"] }, "plan"),
      ev(4, "plan.ready", {
        queries: [
          { id: "q0", text: "topic" },
          { id: "q1", text: "a" },
        ],
      }),
    ]);
    expect(state.phases.plan.counters.hits).toBe(1);
    expect(state.subQueries[0].results).toBe(1);
    expect(state.rounds[0].queries[0].results).toBe(1);
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

  it("applies a terminal event whatever its seq", () => {
    const state = runReducer(initialRunView("r1"), ev(0, "run.cancelled", {} as never));
    expect(state.status).toBe("cancelled");
    expect(state.lastSeq).toBe(0);
    const done = fold([started, ev(2, "run.done", { until: null, totals: {} as never })]);
    expect(runReducer(done, ev(2, "run.done", { until: null, totals: {} as never }))).toEqual(done);
  });
});

describe("applySummary", () => {
  const running = () => fold([started, ev(2, "stage.started", { device: null } as never, "fetch")]);
  const summary = (status: RunView["status"], extra = {}) => ({ status, ...extra });

  it("fails the run and its stage from a failed summary", () => {
    const state = applySummary(
      running(),
      summary("failed", { end_stage: "fetch", error: "no output" }),
    );
    expect(state.status).toBe("failed");
    expect(state.phases.fetch).toMatchObject({ state: "failed", error: "no output" });
    expect(state.failure).toEqual({ stage: "fetch", error: "no output" });
  });

  it("cancels the open phases from a cancelled summary", () => {
    const state = applySummary(running(), summary("cancelled", { end_stage: "fetch" }));
    expect(state.status).toBe("cancelled");
    expect(state.phases.fetch.state).toBe("cancelled");
  });

  it("leaves the view alone for a running summary or an ended view", () => {
    const view = running();
    expect(applySummary(view, summary("running"))).toBe(view);
    const ended = applySummary(view, summary("done"));
    expect(applySummary(ended, summary("failed", { end_stage: "fetch" }))).toBe(ended);
  });
});

describe("research rounds", () => {
  it("folds three rounds with their queries, pages, gap notes, and the stop", () => {
    const state = fold(roundsLog("max"));
    expect(state.rounds.map((r) => [r.round, r.state, r.newPages, r.kept])).toEqual([
      [1, "done", 16, 32],
      [2, "done", 6, 12],
      [3, "done", 4, 8],
    ]);
    expect(state.rounds[0].note).toBe("Benchmarks are thin.");
    expect(state.rounds[0].gap).toBe(2);
    expect(state.rounds[0].uncovered).toEqual(["q4", "q5"]);
    expect(state.rounds[0].missing).toEqual(["setup", "cost"]);
    expect(state.rounds[1].missing).toEqual([]);
    expect(state.rounds[1].queries.map((q) => [q.id, q.results, q.searched])).toEqual([
      ["q6", 1, true],
      ["q7", 1, true],
    ]);
    expect(state.research).toEqual({ planned: 3, ran: 3, reason: "max rounds", note: "" });
    expect(state.phases.fetch).toMatchObject({ state: "done", round: 3, roundsDone: 3 });
    expect(state.phases.gap).toMatchObject({ state: "done", round: 2, roundsDone: 2 });
    expect(state.sources["https://r3-0.test"].round).toBe(3);
  });

  it("records a round with no new sources", () => {
    const state = fold(roundsLog("nonew"));
    expect(state.rounds[1]).toMatchObject({ state: "done", newPages: 0, knownPages: 9 });
    expect(state.rounds[2]).toMatchObject({ state: "done", newPages: 0, knownPages: 3 });
    expect(state.research).toMatchObject({ planned: 4, ran: 3, reason: "no new sources" });
  });

  it("ends without a next round when the gap step wrote no follow-up", () => {
    const state = fold(roundsLog("nofollow"));
    expect(state.rounds.map((r) => r.round)).toEqual([1, 2]);
    expect(state.rounds[1]).toMatchObject({ gap: 0, uncovered: ["q6", "q7"] });
    expect(state.research?.reason).toBe("no follow-ups");
  });

  it("tracks the running round and cancels it", () => {
    let state = fold(roundTwoFetching());
    expect(state.rounds[1]).toMatchObject({ state: "running", stage: "fetch", newPages: 6 });
    expect(state.phases.fetch.round).toBe(2);
    state = runReducer(state, ev(999, "run.cancelled", { stage: "fetch" }));
    expect(state.rounds[1].state).toBe("cancelled");
    expect(state.phases.fetch.state).toBe("cancelled");
  });
});

describe("stage times", () => {
  const at = (seq: number) => Date.UTC(2026, 9, 3, 14, 0, seq);
  const start = (seq: number, stage: string, round = 1) =>
    ev(seq, "stage.started", { device: null, provider: null, round } as never, stage as never);

  it("counts a running stage from its start", () => {
    const state = fold([started, start(2, "fetch")]);
    const time = stageTime(state, "fetch", false, at(10));
    expect(time).toMatchObject({ kind: "time", seconds: 8, live: true });
    expect(timeRow(time)).toMatchObject({ text: "8.0s", tone: "accent" });
    expect(timeBar(state, ["fetch"], () => false, undefined, at(10)).running).toBe(true);
  });

  it("keeps a GPU wait apart from the stage time", () => {
    const waiting = ev(
      2,
      "resource.waiting",
      { device: "gpu0", released_stage: "prefilter" } as never,
      "score",
    );
    let state = fold([started, waiting]);
    expect(timeRow(stageTime(state, "score", false, at(4)))).toMatchObject({
      text: "—",
      wait: "2.0s",
    });
    state = fold([start(7, "score"), stageDone(8, "score", { seconds: 3.3 })], state);
    const row = timeRow(stageTime(state, "score", false, at(20)));
    expect(row).toMatchObject({ text: "3.3s", wait: "+5.0s" });
    expect(row.title).toBe("Stage time 3.3s · plus 5.0s waiting for the GPU");
    const bar = timeBar(state, ["score"], () => false, undefined, at(20));
    expect(bar.all.at(-1)).toMatchObject({ label: "GPU wait", time: "5.0s", note: "before Score" });
  });

  it("sums the rounds of a stage and lists them", () => {
    const state = fold([
      started,
      start(2, "search"),
      stageDone(3, "search", { seconds: 4.1, round: 1 }),
      start(4, "search", 2),
      stageDone(5, "search", { seconds: 3.0, round: 2 }),
      start(6, "search", 3),
      stageDone(7, "search", { seconds: 2.2, round: 3 }),
    ]);
    const row = timeRow(stageTime(state, "search", false, at(30)));
    expect(row.text).toBe("9.3s");
    expect(row.title).toBe("Round 1 4.1s · Round 2 3.0s · Round 3 2.2s · total 9.3s");
    const bar = timeBar(state, ["search"], () => false, undefined, at(30));
    expect(bar.all[0].note).toBe("4.1s + 3.0s + 2.2s");
  });

  it("totals a replayed finished log with the queue time", () => {
    const state = fold([
      started,
      start(2, "plan"),
      stageDone(3, "plan", { seconds: 14.4 }),
      start(4, "write"),
      stageDone(5, "write", { seconds: 11.9 }),
      stageDone(6, "load", { seconds: 0, skipped: true }),
      ev(7, "run.done", { until: null, totals: usage(0) } as never),
    ]);
    const created = new Date(at(-4)).toISOString();
    const bar = timeBar(state, ["load", "plan", "write"], (id) => id === "load", created, at(99));
    expect(fmtDuration(bar.total)).toBe("31.3s");
    expect(bar.running).toBe(false);
    expect(bar.top.map((p) => p.label)).toEqual(["Plan", "Write", "Queue"]);
    expect(bar.all.map((p) => [p.label, p.time])).toEqual([
      ["Queue", "5.0s"],
      ["Load", "skipped"],
      ["Plan", "14.4s"],
      ["Write", "11.9s"],
    ]);
    expect(fmtDuration(125)).toBe("2m 05s");
  });
});

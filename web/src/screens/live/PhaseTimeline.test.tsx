import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEvent } from "../../api/types";
import { ev, stageDone } from "../../test/events";
import { live } from "../../test/fixtures/live";
import { RUN_ID, upTo } from "../../test/fixtures/sample";
import { REWRITE_ID, versions } from "../../test/fixtures/versions";
import { renderWithHelp } from "../../test/help";
import { roundsLog, roundTwoFetching } from "../../test/rounds";
import { viewOf } from "../../test/views";
import { PhaseTimeline } from "./PhaseTimeline";

const all = live.data.events?.[RUN_ID] as RunEvent[];
const card = (label: string) => screen.getByText(label).closest("li") as HTMLElement;

describe("PhaseTimeline", () => {
  it("shows waiting apart from running", () => {
    render(
      <PhaseTimeline
        run={viewOf(upTo(all, (e) => e.type === "stage.started" && e.stage === "score"))}
      />,
    );
    expect(card("Score").dataset.state).toBe("waiting");
    expect(card("Score").textContent).toContain("waiting for GPU · prefilter unloading");
    expect(card("Prefilter").dataset.state).toBe("done");
    expect(card("Prefilter").textContent).toContain("96 of 412 kept");
    expect(card("Fetch").textContent).toContain("fetched 19/22 · 3 failed");
    expect(screen.getAllByRole("listitem")).toHaveLength(9);
    expect(screen.getByRole("button", { name: "Help: Score, waiting for GPU" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Prefilter" })).toBeTruthy();
    for (const item of screen.getAllByRole("listitem"))
      expect(item.hasAttribute("title")).toBe(false);
  });

  it("shows running with its progress", () => {
    render(
      <PhaseTimeline
        run={viewOf(upTo(all, (e) => e.type === "stage.done" && e.stage === "score"))}
      />,
    );
    expect(card("Score").dataset.state).toBe("running");
    expect(card("Score").textContent).toContain("scored 96/96");
    expect(card("Write").textContent).toContain("pending");
  });

  it("names the parent of reused phases and marks skipped ones", () => {
    const fork = versions.data.events?.[REWRITE_ID] as RunEvent[];
    render(<PhaseTimeline run={viewOf(fork)} />);
    expect(card("Plan").dataset.state).toBe("reused");
    expect(card("Plan").textContent).toContain("reused from r_8c21");
    expect(card("Write").dataset.state).toBe("done");
  });

  it("shows phases a recipe skips as done with skipped", () => {
    const started = all[0] as Extract<RunEvent, { type: "run.started" }>;
    const context = { ...started, data: { ...started.data, until: "select" as const } };
    render(<PhaseTimeline run={viewOf([context, stageDone(2, "load", { skipped: true })])} />);
    expect(card("Write").dataset.state).toBe("done");
    expect(card("Write").textContent).toContain("skipped");
    expect(card("Load").textContent).toContain("skipped");
  });

  const begin = all[0];
  const embeddings = "embeddings:bge-small-en-v1.5";
  const prefilterStarted = ev(
    2,
    "stage.started",
    { device: "gpu0", provider: embeddings },
    "prefilter",
  );

  it("tags embeddings that ran as configured with the model", () => {
    render(
      <PhaseTimeline
        run={viewOf([begin, prefilterStarted, stageDone(3, "prefilter", { provider: embeddings })])}
      />,
    );
    const tag = screen.getByRole("button", { name: "Method: bge-small-en-v1.5, details" });
    expect(tag.className).not.toContain("fallback");
  });

  it("marks a prefilter that fell back to BM25 and names the reason", () => {
    const warning = "embeddings prefilter failed, used bm25: connection refused";
    renderWithHelp(
      <PhaseTimeline
        run={viewOf([
          begin,
          prefilterStarted,
          stageDone(3, "prefilter", { provider: "bm25", warnings: [warning] }),
        ])}
        topK={50}
      />,
    );
    const tag = screen.getByRole("button", { name: "Method: BM25 · fallback, details" });
    expect(tag.className).toContain("fallback");
    expect(tag.querySelector("svg")).toBeTruthy();
    fireEvent.mouseEnter(tag);
    const text = screen.getByRole("tooltip").textContent;
    expect(text).toContain("Fallback · keyword (BM25)");
    expect(text).toContain("embeddings (bge-small-en-v1.5)");
    expect(text).toContain("connection refused");
  });

  it("shows no tag on a pending phase", () => {
    render(<PhaseTimeline run={viewOf([begin, prefilterStarted])} />);
    expect(card("Score").querySelector("[data-help^='m-']")).toBeNull();
    expect(card("Prefilter").querySelector("[data-help='m-prefilter']")).toBeTruthy();
  });

  it("shows the prefilter detail while running", () => {
    render(<PhaseTimeline run={viewOf([begin, prefilterStarted])} topK={50} />);
    expect(card("Prefilter").textContent).toContain("top 50 per sub-query");
  });

  it("shows the prefilter detail with passthrough sub-queries once done", () => {
    const done = stageDone(3, "prefilter", { provider: embeddings, passthrough: ["q4", "q5"] });
    render(<PhaseTimeline run={viewOf([begin, prefilterStarted, done])} topK={50} />);
    expect(card("Prefilter").textContent).toContain("top 50/sub-query · q4, q5 passthrough");
  });
});

describe("PhaseTimeline rounds", () => {
  it("shows the round on loop cards and the Gap card in a multi-round run", () => {
    render(<PhaseTimeline run={viewOf(roundTwoFetching())} rounds={3} />);
    expect(card("Fetch").dataset.state).toBe("running");
    expect(card("Fetch").textContent).toContain("round 2/3");
    expect(card("Search").textContent).toContain("round 2 done");
    expect(card("Gap").textContent).toContain("2 follow-ups");
    expect(card("Gap").textContent).toContain("after round 1");
    expect(screen.getAllByRole("listitem")).toHaveLength(10);
  });

  it("ends with the rounds each card ran", () => {
    render(<PhaseTimeline run={viewOf(roundsLog("coverage"))} rounds={3} />);
    expect(card("Score").textContent).toContain("2 rounds");
    expect(card("Gap").textContent).toContain("2 of 3 rounds");
    expect(card("Gap").textContent).toContain("model judged coverage sufficient");
  });

  it("has no Gap card in a single-round run", () => {
    render(<PhaseTimeline run={viewOf(all)} />);
    expect(screen.queryByText("Gap")).toBeNull();
    expect(card("Fetch").textContent).not.toContain("round");
  });
});

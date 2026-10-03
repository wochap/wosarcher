import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEvent } from "../../api/types";
import { stageDone } from "../../test/events";
import { live } from "../../test/fixtures/live";
import { RUN_ID, upTo } from "../../test/fixtures/sample";
import { REWRITE_ID, versions } from "../../test/fixtures/versions";
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
});

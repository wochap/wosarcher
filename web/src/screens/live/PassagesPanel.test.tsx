import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEvent } from "../../api/types";
import { ev } from "../../test/events";
import { finished } from "../../test/fixtures/finished";
import { live } from "../../test/fixtures/live";
import { CONTEXT, RUN_ID, upTo } from "../../test/fixtures/sample";
import { openScenario } from "../../test/scenario";
import { viewOf } from "../../test/views";
import { PassagesPanel } from "./PassagesPanel";

const all = live.data.events?.[RUN_ID] as RunEvent[];

function panel(
  events: RunEvent[],
  context = null as typeof CONTEXT | null,
  configuredScorer?: string,
) {
  render(
    <PassagesPanel
      run={viewOf(events, RUN_ID)}
      context={context}
      marker="numeric"
      rejected={null}
      showRejected={false}
      onToggle={() => {}}
      configuredScorer={configuredScorer}
    />,
  );
}

const scored = (threshold: number | null, display: number | null, scorer = "jev") =>
  ev(
    5,
    "passages.scored",
    {
      query_id: "q1",
      scorer,
      scored: 3,
      kept: 1,
      threshold_display: threshold,
      passages: [
        {
          chunk_id: "c1",
          source_id: "s1",
          title: "A",
          uri: "https://www.example.org/a",
          heading_path: ["Intro", "Scope"],
          text: "Some text.",
          display,
        },
      ],
    },
    "score",
  );

describe("PassagesPanel", () => {
  it("places the threshold marker at the scorer's display threshold", () => {
    panel([scored(0.5, 0.8)]);
    const marker = screen.getByTitle("threshold 0.50");
    expect(marker.style.left).toBe("50%");
    expect(screen.getByText("0.80")).toBeTruthy();
    expect(screen.getByText("above threshold")).toBeTruthy();
    expect(screen.getByText("example.org")).toBeTruthy();
    expect(screen.getByText(/Intro › Scope/)).toBeTruthy();
    expect(screen.getByText("3/3 scored · ≥ 0.50")).toBeTruthy();
  });

  it("shows a passthrough passage with a dash and no bar", () => {
    panel([scored(null, null, "passthrough")]);
    expect(screen.getByText("–")).toBeTruthy();
    expect(screen.queryByTitle(/threshold/)).toBeNull();
  });

  it("labels selected passages with their citation and summarizes kept of scored", () => {
    panel(all, CONTEXT);
    expect(screen.getByText("14 kept of 96 scored · ≥ 0.60")).toBeTruthy();
    const best = screen.getAllByRole("article")[0];
    expect(within(best).getByText("0.94")).toBeTruthy();
    expect(within(best).getByText("[1]")).toBeTruthy();
  });

  it("explains an empty panel", () => {
    panel(upTo(all, (e) => e.type === "stage.started" && e.stage === "score"));
    expect(
      screen.getByText("Scorer is waiting for the GPU while the embeddings model unloads."),
    ).toBeTruthy();
  });

  it("shows rejected passages at half opacity when R is pressed", async () => {
    await openScenario({ ...finished, screen: "live" });
    expect(screen.getAllByRole("article")).toHaveLength(14);
    await act(async () => {
      fireEvent.keyDown(window, { key: "r" });
    });
    const rejected = await screen.findAllByText(/rejected · below 0.60/);
    expect(rejected).toHaveLength(8);
    const card = rejected[0].closest("article") as HTMLElement;
    expect(card.dataset.kept).toBe("false");
    expect(within(card).getByText("0.52")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Rejected/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("tags the scorer and the threshold with their help", () => {
    panel(all, CONTEXT, "rerank");
    expect(screen.getByText("rerank")).toBeTruthy();
    expect(screen.getByText("14 kept of 96 scored · ≥ 0.60")).toBeTruthy();
    for (const label of ["Scorer", "Score and threshold", "Rejected passages"])
      expect(screen.getByRole("button", { name: `Help: ${label}` })).toBeTruthy();
  });

  it("tags the scorer jev", () => {
    panel([scored(0.6, 0.8)], null, "jev");
    expect(screen.getByText("jev")).toBeTruthy();
  });

  it("marks a fallback scorer", () => {
    panel([scored(0.5, 0.8, "bm25")], null, "rerank");
    expect(screen.getByText("bm25 · fallback")).toBeTruthy();
  });

  it("leaves out the threshold when queries differ", () => {
    const second = {
      ...scored(0.7, 0.9),
      seq: 6,
      data: { ...scored(0.7, 0.9).data, query_id: "q2" },
    } as RunEvent;
    panel([scored(0.5, 0.8), second]);
    expect(screen.queryByText(/≥/)).toBeNull();
  });
});

import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RunEvent } from "../../api/types";
import type { PassageItem } from "../../run/scores";
import { ev } from "../../test/events";
import { finished } from "../../test/fixtures/finished";
import { live } from "../../test/fixtures/live";
import { CONTEXT, RUN_ID, SELECT_SKIPS, upTo } from "../../test/fixtures/sample";
import { renderWithHelp } from "../../test/help";
import { openScenario } from "../../test/scenario";
import { viewOf } from "../../test/views";
import { type PassageFilter, PassagesPanel } from "./PassagesPanel";

const all = live.data.events?.[RUN_ID] as RunEvent[];
const tooltip = () => screen.getByRole("tooltip");

type Options = {
  context?: typeof CONTEXT | null;
  configuredScorer?: string;
  filter?: PassageFilter;
  notKept?: PassageItem[] | null;
  skips?: typeof SELECT_SKIPS | null;
  onOpen?: (p: PassageItem) => void;
};

function panel(events: RunEvent[], options: Options = {}) {
  renderWithHelp(
    <PassagesPanel
      run={viewOf(events, RUN_ID)}
      context={options.context ?? null}
      marker="numeric"
      notKept={options.notKept ?? null}
      skips={options.skips ?? null}
      filter={options.filter ?? "kept"}
      onFilter={() => {}}
      configuredScorer={options.configuredScorer}
      config={{ prefilterTopK: 50, scoreTopK: 10, maxPerSource: 1 }}
      onOpen={options.onOpen}
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

const notKept = (
  chunk_id: string,
  display: number,
  dropped: PassageItem["dropped"],
): PassageItem => ({
  chunk_id,
  source_id: "s2",
  title: "B",
  uri: "https://b.example.com/x",
  heading_path: ["Body"],
  text: `Text of ${chunk_id}.`,
  display,
  queryId: "q1",
  scorer: "rerank",
  threshold: 0.6,
  kept: false,
  dropped,
});

const badge = (card: HTMLElement) => card.querySelector("[data-fate]") as HTMLElement;
const card = (text: string) => screen.getByText(text).closest("article") as HTMLElement;
const funnelText = () =>
  within(screen.getByRole("group", { name: "Pipeline" }))
    .getAllByRole("button")
    .slice(0, 4)
    .map((b) => b.textContent)
    .join(" › ");

describe("PassagesPanel", () => {
  it("places the threshold marker at the scorer's display threshold", () => {
    panel([scored(0.5, 0.8)], { filter: "all" });
    const marker = screen.getByTitle("threshold 0.50");
    expect(marker.style.left).toBe("50%");
    expect(screen.getByText("0.80")).toBeTruthy();
    expect(screen.getByText("≥ 0.50")).toBeTruthy();
    expect(screen.getByText("example.org")).toBeTruthy();
    expect(screen.getByText(/Intro › Scope/)).toBeTruthy();
  });

  it("shows a passthrough passage with a dash and no bar", () => {
    panel([scored(null, null, "passthrough")], { filter: "all" });
    expect(within(screen.getByRole("article")).getByText("–")).toBeTruthy();
    expect(screen.queryByTitle(/threshold/)).toBeNull();
  });

  it("opens the Kept filter of a finished run with every kept passage and its fate", async () => {
    await openScenario({ ...finished, screen: "live" });
    const radio = screen.getByRole("radio", { name: /^Kept/ }) as HTMLInputElement;
    expect(radio.checked).toBe(true);
    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(16);
    expect(within(cards[0]).getByText("0.94")).toBeTruthy();
    expect(within(cards[0]).getByText("[1]")).toBeTruthy();
    expect(await screen.findByText("source cap")).toBeTruthy();
    expect(badge(card("source cap")).dataset.fate).toBe("srccap");
    expect(card("source cap").dataset.dim).toBe("true");
    expect(card("over budget").dataset.dim).toBe("true");
  });

  it("cycles Cited, Kept, and All with R", async () => {
    await openScenario({ ...finished, screen: "live" });
    const checked = () =>
      (screen.getAllByRole("radio") as HTMLInputElement[]).find((r) => r.checked)?.parentElement
        ?.textContent;
    expect(checked()).toBe("Kept16");
    for (const next of ["All96", "Cited14", "Kept16"]) {
      await act(async () => {
        fireEvent.keyDown(window, { key: "r" });
      });
      expect(checked()).toBe(next);
    }
  });

  it("shows query-capped passages and collapses the ones below the threshold in All", async () => {
    await openScenario({ ...finished, screen: "live" });
    await act(async () => {
      fireEvent.click(screen.getByRole("radio", { name: /^All/ }));
    });
    const capped = await screen.findByText("query cap");
    const article = capped.closest("article") as HTMLElement;
    expect(within(article).getByText("0.60")).toBeTruthy();
    expect(within(article).getByText("q2")).toBeTruthy();
    expect(article.dataset.dim).toBe("true");
    expect(screen.queryByText(/^below/)).toBeNull();
    expect(screen.getByText("8 more below 0.60 not listed (0.14–0.52)")).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Show" }));
    });
    const below = screen.getAllByText("below 0.60");
    expect(below).toHaveLength(8);
    expect((below[0].closest("article") as HTMLElement).dataset.kept).toBe("false");
    expect(screen.getByRole("button", { name: "Hide" })).toBeTruthy();
  });

  it("tells a query cap from a threshold rejection", () => {
    panel(all, {
      context: CONTEXT,
      filter: "all",
      notKept: [notKept("c90", 0.65, "query_cap"), notKept("c91", 0.3, "threshold")],
    });
    expect(badge(card("Text of c90.")).textContent).toBe("query capq1");
    expect(screen.getByText("1 more below 0.60 not listed (0.30–0.30)")).toBeTruthy();
    const cited = card(CONTEXT.passages[13].text);
    expect(badge(cited).textContent).toBe(`cited[${CONTEXT.passages[13].n}]`);
  });

  it("shows select skips once select is done", () => {
    panel(all, { context: CONTEXT, skips: SELECT_SKIPS });
    expect(badge(card("source cap")).dataset.fate).toBe("srccap");
    expect(badge(card("over budget")).dataset.fate).toBe("budget");
  });

  it("shows kept passages as selecting before select is done", () => {
    panel(upTo(all, (e) => e.type === "stage.done" && e.stage === "select"));
    expect(screen.getAllByText("kept · selecting")).toHaveLength(16);
    expect(funnelText()).toBe("412chunks › 96scored › 16kept › –cited");
    expect(screen.getByRole("button", { name: "pending cited, help" })).toBeTruthy();
  });

  it("reads the funnel of a finished run", () => {
    panel(all, { context: CONTEXT });
    expect(funnelText()).toBe("412chunks › 96scored › 16kept › 14cited");
  });

  it("builds the funnel help from the run's configuration", () => {
    panel(all, { context: CONTEXT });
    fireEvent.focus(screen.getByRole("button", { name: "16 kept, help" }));
    expect(tooltip().textContent).toBe(
      "KeptScored at least 0.60 (threshold) and in the top 10 of their sub-query (query cap).",
    );
  });

  it("lists the six fates in the legend", () => {
    panel(all, { context: CONTEXT });
    fireEvent.mouseEnter(screen.getByRole("button", { name: "Help: Passage fates" }));
    const rows = within(tooltip()).getAllByRole("listitem");
    expect(rows.map((r) => r.textContent?.split(" ")[0])).toEqual([
      "cited",
      "source",
      "over",
      "query",
      "below",
      "prefiltered",
    ]);
    expect(rows[1].textContent).toBe(
      "source cap Kept, but its source already has the maximum of 1 cited passage.",
    );
    expect(rows[3].textContent).toBe(
      "query cap · q1 At or above 0.60, but its sub-query already had 10 better passages.",
    );
  });

  it("explains the Cited and Kept filters before their stage is done", () => {
    const scoring = upTo(all, (e) => e.type === "stage.done" && e.stage === "score");
    panel(scoring, { filter: "kept" });
    expect(
      screen.getByText(
        "Kept passages are known once scoring finishes. Switch to All to watch scores arrive.",
      ),
    ).toBeTruthy();
    panel(scoring, { filter: "cited" });
    expect(
      screen.getByText(
        "Citations are assigned when Select finishes. Switch to All to watch scores arrive.",
      ),
    ).toBeTruthy();
  });

  it("explains an empty panel", () => {
    panel(upTo(all, (e) => e.type === "stage.started" && e.stage === "score"));
    expect(
      screen.getByText("Scorer is waiting for the GPU while the embeddings model unloads."),
    ).toBeTruthy();
  });

  it("opens a card with Enter when it has an open action", () => {
    const onOpen = vi.fn();
    panel([scored(0.5, 0.8)], { filter: "all", onOpen });
    const open = screen.getByRole("button", { name: "0.80, example.org. Open source" });
    fireEvent.click(open);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ chunk_id: "c1" }));
  });

  it("tags the scorer with its help", () => {
    panel(all, { context: CONTEXT, configuredScorer: "rerank" });
    expect(screen.getByText("rerank")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Scorer" })).toBeTruthy();
  });

  it("tags the scorer jev", () => {
    panel([scored(0.6, 0.8)], { configuredScorer: "jev" });
    expect(screen.getByText("jev")).toBeTruthy();
  });

  it("marks a fallback scorer", () => {
    panel([scored(0.5, 0.8, "bm25")], { configuredScorer: "rerank" });
    expect(screen.getByText("bm25 · fallback")).toBeTruthy();
  });

  it("names the threshold in words when queries differ", () => {
    const second = {
      ...scored(0.7, 0.9),
      seq: 6,
      data: { ...scored(0.7, 0.9).data, query_id: "q2" },
    } as RunEvent;
    panel([scored(0.5, 0.8), second], {
      filter: "all",
      notKept: [notKept("c90", 0.2, "threshold")],
    });
    expect(screen.getByText("1 more below the threshold not listed (0.20–0.20)")).toBeTruthy();
  });
});

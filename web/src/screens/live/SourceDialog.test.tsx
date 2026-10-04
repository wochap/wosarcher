import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChunkFate, SourceChunk, SourceView } from "../../api/types";
import { ApiContext, type Ui, UiContext } from "../../app/context";
import { type FakeApi, fakeApi } from "../../test/fakeApi";
import { RUN_ID, sourceViews, summary, TRUNCATED_SOURCE } from "../../test/fixtures/sample";
import { SourceDialog } from "./SourceDialog";

const QUERIES = [
  { id: "q1", text: "first sub-query" },
  { id: "q2", text: "second sub-query" },
  { id: "q3", text: "third sub-query" },
];

const kept = { query_id: "q1", display: 0.8, rank: 2, ranked: 14, kept_in_query: 10 };
const FATES: ChunkFate[] = [
  { ...kept, kind: "cited", n: 3 },
  { ...kept, kind: "kept" },
  { ...kept, kind: "source_cap" },
  { ...kept, kind: "budget", tokens_needed: 410, tokens_left: 120 },
  { query_id: "q1", display: 0.65, rank: 11, ranked: 14, kept_in_query: 10, kind: "query_cap" },
  { query_id: "q2", display: 0.3, kind: "below_threshold" },
  { kind: "prefiltered" },
  { kind: "pending" },
  { ...kept, kind: "cited", n: 7 },
];

const WHY = [
  "Kept: rank 2 of 10 in q1; cited as [3].",
  "Kept: rank 2 of 10 in q1. Selection is running.",
  "Kept: rank 2 of 10 in q1; not cited: this source already has 3 cited passages (cap 3 per source).",
  "Kept: rank 2 of 10 in q1; not cited: needs 410 tokens, 120 were left in the budget.",
  "Scored 0.65 in q1 but ranked 11 of 14 above 0.50; q1 keeps only its top 10.",
  "Scored 0.30 in q2, below the 0.50 threshold.",
  "Not scored: outside the top 50 for every sub-query.",
  "Waiting for the scorer.",
];

function chunk(fate: ChunkFate, i: number): SourceChunk {
  return {
    chunk_id: `c${i + 1}`,
    position: i < 4 ? i : i + 2,
    heading_path: i < 4 ? ["Intro", `Part ${i + 1}`] : ["Results"],
    text: `Chunk ${i + 1} text.`,
    removed_before: i === 4 ? 2 : 0,
    queries: [
      { query_id: "q1", state: fate.kind === "query_cap" ? "query_cap" : "kept", display: 0.8 },
      { query_id: "q2", state: "other_query", display: 0.4 },
      { query_id: "q3", state: "not_in_results" },
    ],
    fate,
  };
}

const VIEW: SourceView = {
  source: {
    source_id: "s1",
    kind: "web",
    uri: "https://www.example.org/paper",
    title: "A paper",
  },
  truncated: false,
  queries: QUERIES,
  threshold: 0.5,
  query_cap: 10,
  source_cap: 3,
  chunks: FATES.map(chunk),
};

function setup(
  options: { sourceId?: string; chunkId?: string; isPhone?: boolean; slow?: boolean } = {},
) {
  const api: FakeApi = fakeApi({
    runs: [summary()],
    sources: { [RUN_ID]: { s1: VIEW, ...sourceViews() } },
  });
  let resolve: (view: SourceView) => void = () => {};
  if (options.slow) api.source = () => new Promise((r) => (resolve = r));
  const ui = { isPhone: options.isPhone ?? false, overlay: () => () => {} } as Partial<Ui> as Ui;
  const onClose = vi.fn();
  render(
    <ApiContext.Provider value={{ api }}>
      <UiContext.Provider value={ui}>
        <SourceDialog
          runId={RUN_ID}
          sourceId={options.sourceId ?? "s1"}
          chunkId={options.chunkId ?? "c3"}
          marker="numeric"
          context={null}
          prefilterTopK={50}
          onClose={onClose}
        />
      </UiContext.Provider>
    </ApiContext.Provider>,
  );
  return { api, onClose, resolve: (view: SourceView) => resolve(view) };
}

const footer = () => screen.getByText(/^Chunk \d+ of \d+$/).textContent;
const why = (dialog: HTMLElement) =>
  within(dialog).getByText(/^(Kept|Scored|Not scored|Waiting)/).textContent;

describe("SourceDialog", () => {
  it("shows the header, the selected chunk's fate, and the sub-query chips", async () => {
    setup({ chunkId: "c5" });
    const dialog = await screen.findByRole("dialog", { name: "A paper" });
    expect(within(dialog).getByText("example.org")).toBeTruthy();
    const link = within(dialog).getByRole("link", { name: /Open original/ });
    expect(link.getAttribute("href")).toBe("https://www.example.org/paper");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(within(dialog).getByText("9 chunks · 7 scored · 2 cited")).toBeTruthy();
    expect(why(dialog)).toBe(WHY[4]);
    const chips = within(within(dialog).getByRole("list", { name: "Sub-queries" })).getAllByRole(
      "listitem",
    );
    expect(chips.map((c) => c.textContent)).toEqual([
      "q10.80query cap",
      "q20.40counted in q1",
      "q3not in results",
    ]);
    expect(chips[0].dataset.primary).toBe("true");
    expect(chips[0].getAttribute("title")).toBe("q1: first sub-query");
    expect(within(dialog).getByText("2 near-duplicate chunks removed")).toBeTruthy();
    expect(
      within(dialog)
        .getAllByRole("heading")
        .map((h) => h.textContent),
    ).toEqual(["Intro", "Results"]);
    expect(footer()).toBe("Chunk 5 of 9");
  });

  it("writes the why line of every fate", async () => {
    setup({ chunkId: "c1" });
    const dialog = await screen.findByRole("dialog", { name: "A paper" });
    for (const [i, line] of WHY.entries()) {
      fireEvent.click(dialog.querySelector(`[data-chunk="c${i + 1}"]`) as HTMLElement);
      expect(why(dialog)).toBe(line);
    }
  });

  it("retargets by click and moves with the arrow keys and Prev and Next", async () => {
    setup({ chunkId: "c3" });
    const dialog = await screen.findByRole("dialog", { name: "A paper" });
    expect(footer()).toBe("Chunk 3 of 9");
    fireEvent.click(dialog.querySelector('[data-chunk="c5"]') as HTMLElement);
    expect(footer()).toBe("Chunk 5 of 9");
    expect(dialog.querySelector('[data-chunk="c5"]')?.getAttribute("aria-current")).toBe("true");
    fireEvent.keyDown(dialog, { key: "ArrowUp" });
    expect(footer()).toBe("Chunk 4 of 9");
    fireEvent.keyDown(dialog, { key: "ArrowDown" });
    fireEvent.keyDown(dialog, { key: "ArrowDown" });
    expect(footer()).toBe("Chunk 6 of 9");
    const prev = screen.getByRole("button", { name: "Prev" }) as HTMLButtonElement;
    const next = screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;
    for (let i = 0; i < 10; i++) fireEvent.click(next);
    expect(footer()).toBe("Chunk 9 of 9");
    expect(next.disabled).toBe(true);
    for (let i = 0; i < 10; i++) fireEvent.click(prev);
    expect(footer()).toBe("Chunk 1 of 9");
    expect(prev.disabled).toBe(true);
    fireEvent.keyDown(dialog.querySelector('[data-chunk="c2"]') as HTMLElement, { key: "Enter" });
    expect(footer()).toBe("Chunk 2 of 9");
  });

  it("shows a skeleton with Prev and Next disabled while loading", async () => {
    const { resolve } = setup({ slow: true });
    expect(screen.getByText("Loading cleaned text…")).toBeTruthy();
    expect(screen.getAllByTestId("source-skeleton")).toHaveLength(5);
    expect((screen.getByRole("button", { name: "Prev" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => resolve(VIEW));
    expect(screen.queryByText("Loading cleaned text…")).toBeNull();
  });

  it("shows a load error inline with Retry", async () => {
    setup({ sourceId: "missing" });
    expect((await screen.findByRole("alert")).textContent).toMatch(/no source missing/);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/no source missing/);
  });

  it("shows an attached file without a link", async () => {
    setup({ sourceId: "f1", chunkId: "f1c0" });
    const dialog = await screen.findByRole("dialog", { name: "bench-3060.md" });
    expect(within(dialog).getByText("Attached file · no URL")).toBeTruthy();
    expect(within(dialog).queryByRole("link", { name: /Open original/ })).toBeNull();
    expect(why(dialog)).toBe("Not scored: outside the top 50 for every sub-query.");
  });

  it("shows the truncation note and the end marker", async () => {
    setup({ sourceId: TRUNCATED_SOURCE, chunkId: "c19" });
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("note").textContent).toMatch(/Fetch stopped/);
    expect(within(dialog).getByText("Fetch stopped here")).toBeTruthy();
  });

  it("is a full-screen sheet on phones", async () => {
    setup({ isPhone: true });
    const dialog = await screen.findByRole("dialog", { name: "A paper" });
    expect(dialog.className).toMatch(/sheet/);
    expect(screen.queryByText("move")).toBeNull();
  });
});

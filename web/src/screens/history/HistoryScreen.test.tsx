import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

const rowOf = (text: string) =>
  screen
    .getAllByText(text)
    .map((e) => e.closest("tr"))
    .find(Boolean) as HTMLElement;
const rows = () => screen.getAllByRole("row").slice(1);

afterEach(() => vi.useRealTimers());

async function open(api = fakeApi()) {
  renderApp({ hash: "#/history", api });
  await screen.findByRole("heading", { name: "Run history" });
  await screen.findAllByRole("row");
  return api;
}

describe("HistoryScreen", () => {
  it("lists runs newest first from one GET /api/runs", async () => {
    const api = await open();
    expect(screen.getByText("8")).toBeTruthy();
    expect(rows()[0].textContent).toContain("speculative decoding");
    // Only the followed run's stream reads its detail; rows need nothing beyond the list.
    expect(callsTo(api, "getRun")).toEqual([["r_8c21"]]);
  });

  it("shows recipe, status, duration, and cost per row", async () => {
    await open();
    const running = rowOf("Running");
    expect(within(running).getAllByText("–")).toHaveLength(2);
    const done = rowOf("Rust async cancellation safety patterns with tokio::select!");
    expect(done.textContent).toContain("4:05");
    expect(done.textContent).toContain("$0.008");
    expect(done.textContent).toContain("report");
    expect(
      rowOf("What changed in the Python 3.13 free-threaded build for C extensions?").textContent,
    ).toContain("context");
    expect(rowOf("Failed").textContent).toContain("llama.cpp");
    expect(rowOf("Cancelled").textContent).toContain("SQLite");
    expect(rowOf("Interrupted").textContent).toContain("Embedding models");
  });

  it("shows an answer run's recipe and filters by it", async () => {
    const api = fakeApi();
    const run = api.data.runs.find((r) =>
      r.query.startsWith("Rust async"),
    ) as (typeof api.data.runs)[0];
    run.writing = { ...run.writing, format: "answer" };
    await open(api);
    expect(
      rowOf("Rust async cancellation safety patterns with tokio::select!").textContent,
    ).toContain("answer");
    fireEvent.click(screen.getByLabelText("answer"));
    expect(rows()).toHaveLength(1);
    expect(rows()[0].textContent).toContain("Rust async");
  });

  it("shows a fork's parent and changed writing options", async () => {
    await open();
    const fork = screen.getByText("r_7f3a").closest("div") as HTMLElement;
    expect(fork.textContent).toBe("rewrite of r_7f3a · Explanatory · 300 words");
    expect(within(fork).getByRole("button", { name: "Help: Rewrite marker" })).toBeTruthy();
  });

  it("has help after the Recipe and Cost headers", async () => {
    await open();
    expect(screen.getByRole("button", { name: "Help: Recipe" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Cost" })).toBeTruthy();
  });

  it("filters by search, status, and recipe, and clears the filters", async () => {
    await open();
    fireEvent.change(screen.getByLabelText("Search runs"), { target: { value: "PGVECTOR" } });
    expect(rows()).toHaveLength(2);
    fireEvent.click(screen.getByLabelText("Failed"));
    expect(screen.getByText("No runs match")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(rows()).toHaveLength(8);
    fireEvent.click(screen.getByLabelText("Failed"));
    expect(rows()).toHaveLength(2);
    fireEvent.click(screen.getByLabelText("All"));
    fireEvent.click(screen.getByLabelText("context"));
    expect(rows()).toHaveLength(2);
  });

  it("shows the empty state with New run", async () => {
    renderApp({ hash: "#/history", api: fakeApi({ runs: [] }) });
    expect(await screen.findByText("No runs yet")).toBeTruthy();
    expect(
      screen.getByText("Finished, failed and cancelled runs are kept here with their reports."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "New run" }));
    expect(window.location.hash).toBe("#/new");
  });

  it("opens completed runs on Report and others on Live", async () => {
    await open();
    fireEvent.click(
      within(rowOf("Rust async cancellation safety patterns with tokio::select!")).getByRole(
        "button",
        { name: "Open" },
      ),
    );
    expect(window.location.hash).toBe("#/runs/r_7d11");
    window.location.hash = "#/history";
    await screen.findByRole("heading", { name: "Run history" });
    fireEvent.click(within(rowOf("Failed")).getByRole("button", { name: "Open" }));
    expect(window.location.hash).toBe("#/live/r_7e2c");
  });

  it("reruns through POST /api/runs/{id}/rerun and shows the new run live", async () => {
    const api = await open();
    await act(async () => {
      fireEvent.click(within(rowOf("Failed")).getByRole("button", { name: "Rerun" }));
    });
    expect(callsTo(api, "rerunRun")).toEqual([["r_7e2c"]]);
    expect(window.location.hash).toBe("#/live/r_new1");
  });

  it("hides a deleted row, and Undo within 6 s restores it without a request", async () => {
    const api = await open();
    vi.useFakeTimers();
    fireEvent.click(within(rowOf("Cancelled")).getByRole("button", { name: "Delete" }));
    expect(screen.queryByText("Cancelled", { selector: "span" })).toBeNull();
    expect(screen.getByText("Run deleted")).toBeTruthy();
    act(() => vi.advanceTimersByTime(5000));
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(rowOf("Cancelled")).toBeTruthy();
    await act(async () => vi.advanceTimersByTime(2000));
    expect(callsTo(api, "deleteRun")).toHaveLength(0);
  });

  it("deletes on the server when the toast expires", async () => {
    const api = await open();
    vi.useFakeTimers();
    fireEvent.click(within(rowOf("Cancelled")).getByRole("button", { name: "Delete" }));
    await act(async () => vi.advanceTimersByTime(6000));
    expect(callsTo(api, "deleteRun")).toEqual([["r_7b77"]]);
    expect(rows()).toHaveLength(7);
  });
});

describe("HistoryScreen depth tags", () => {
  it("shows each run's depth, Standard when it has none", async () => {
    const api = fakeApi();
    api.data.runs[0] = { ...api.data.runs[0], depth: "exhaustive" };
    api.data.runs[1] = { ...api.data.runs[1], depth: null };
    await open(api);
    expect(within(rows()[0]).getByText("Exhaustive")).toBeTruthy();
    expect(within(rows()[1]).getByText("Standard")).toBeTruthy();
  });
});

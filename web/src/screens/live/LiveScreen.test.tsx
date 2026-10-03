import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { live } from "../../test/fixtures/live";
import { loading } from "../../test/fixtures/loading";
import { otherRuns, RUN_ID } from "../../test/fixtures/sample";
import { renderApp } from "../../test/renderApp";
import { openScenario } from "../../test/scenario";

describe("LiveScreen", () => {
  it("shows the queued state", async () => {
    await openScenario(loading);
    expect(screen.getByText("Connecting")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch(
      /^Connecting to ws:\/\/.+ · queued, waiting for a free worker…$/,
    );
    expect(screen.getAllByTestId("skeleton")).toHaveLength(6);
    expect(screen.getByText("Waiting for the planner…")).toBeTruthy();
    expect(screen.getByText("Waiting for the run to start.")).toBeTruthy();
    const phases = within(screen.getByRole("list", { name: "Phases" })).getAllByRole("listitem");
    expect(phases.every((p) => p.dataset.state === "pending")).toBe(true);
  });

  it("shows the empty state with no followed run", async () => {
    renderApp({ hash: "#/live", api: fakeApi({ runs: otherRuns }) });
    expect(await screen.findByRole("heading", { name: "No run in progress" })).toBeTruthy();
    fireEvent.click(within(screen.getByRole("main")).getByRole("button", { name: /New run/ }));
    expect(window.location.hash).toBe("#/new");
  });

  it("shows a completed run with Open report", async () => {
    await openScenario(live);
    expect(screen.getByText("Completed")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    expect(await screen.findByRole("heading", { name: "Recommendations" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open report" }));
    expect(window.location.hash).toBe(`#/runs/${RUN_ID}`);
  });

  it("sends Cancel while running and changes only when the run is cancelled", async () => {
    const events = live.data.events?.[RUN_ID] ?? [];
    const { api } = await openScenario(live, { events: events.slice(0, 20) });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    });
    expect(callsTo(api, "cancelRun")).toEqual([[RUN_ID]]);
    expect(screen.getByText("Running")).toBeTruthy();
  });

  it("shows the hovered citation's passage", async () => {
    await openScenario(live);
    const chip = (await screen.findAllByRole("button", { name: "Citation 3, show passage" }))[0];
    act(() => {
      fireEvent.mouseEnter(chip);
    });
    expect(screen.getByRole("tooltip").textContent).toContain("On the RTX 3060");
    act(() => {
      fireEvent.keyDown(window, { key: "Escape" });
    });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});

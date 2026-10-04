import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunStatus } from "../../api/types";
import { FakeWebSocket } from "../../test/FakeWebSocket";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { failure } from "../../test/fixtures/failure";
import { live } from "../../test/fixtures/live";
import { loading } from "../../test/fixtures/loading";
import { otherRuns, RUN_ID, upTo } from "../../test/fixtures/sample";
import { renderApp } from "../../test/renderApp";
import { openScenario, play, socketsFor } from "../../test/scenario";

afterEach(() => vi.useRealTimers());

/** The failure scenario before its last two events, with the summary status `status()`. */
async function failingRun(status: () => RunStatus) {
  const api = fakeApi(failure.data);
  const getRun = api.getRun.bind(api);
  api.getRun = async (id) => ({ ...(await getRun(id)), status: status() });
  const events = api.data.events[RUN_ID];
  await openScenario(failure, { api, events: events.slice(0, -2) });
  return api;
}

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

  it("shows a run that already failed when Cancel answers run_not_active", async () => {
    let status: RunStatus = "running";
    const api = await failingRun(() => status);
    expect(screen.getByText("Running")).toBeTruthy();
    status = "failed";
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    });
    expect(callsTo(api, "cancelRun")).toEqual([[RUN_ID]]);
    expect(await screen.findByText("Failed")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    expect(screen.getByRole("button", { name: "Rerun" })).toBeTruthy();
    expect(screen.queryByText(/not queued or running/)).toBeNull();
  });

  it("disables Cancel while the request is in flight", async () => {
    const api = await failingRun(() => "running");
    api.cancelRun = () => new Promise(() => {});
    const button = screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement;
    await act(async () => {
      fireEvent.click(button);
    });
    expect(button.disabled).toBe(true);
  });

  it("shows live updates unavailable when the upgrade is refused", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = fakeApi(live.data);
    renderApp({ hash: `#/live/${RUN_ID}`, api });
    const texts: string[] = [];
    const close = async (wait: number) => {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(wait);
        socketsFor(RUN_ID).at(-1)?.serverClose(1006);
        await vi.advanceTimersByTimeAsync(0);
      });
      texts.push(screen.queryByRole("status")?.textContent ?? "");
    };
    await close(0);
    for (const wait of [2000, 4000, 8000]) await close(wait);
    expect(texts.at(-1)).toMatch(/^Live updates unavailable\./);
    expect(texts.some((t) => t.includes("Replaying"))).toBe(false);
    expect(screen.getAllByText("Live updates unavailable").length).toBeGreaterThan(0);
  });

  it("shows Run not found when the socket closes 4404", async () => {
    renderApp({ hash: "#/live/r_gone", api: fakeApi({ runs: otherRuns }) });
    await act(async () => {
      FakeWebSocket.last().serverClose(4404);
    });
    expect(await screen.findByRole("heading", { name: "Run not found" })).toBeTruthy();
    expect(
      screen.getByText("Run r_gone does not exist on this server. It may have been deleted."),
    ).toBeTruthy();
    expect(screen.queryByText(/^seq /)).toBeNull();
  });

  it("opens a passage's source from the keyboard and returns focus on Escape", async () => {
    const { api } = await openScenario(live);
    const card = (await screen.findAllByRole("button", { name: /Open source$/ }))[0];
    card.focus();
    // Enter on a focused button activates it as a click.
    fireEvent.click(card);
    const dialog = await screen.findByRole("dialog");
    expect(callsTo(api, "source")).toEqual([[RUN_ID, "s11"]]);
    expect(dialog.querySelector('[data-chunk="c1"]')?.getAttribute("aria-current")).toBe("true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await vi.waitFor(() => expect(document.activeElement).toBe(card));
  });

  it("reloads the open source when a stage finishes and keeps the selection", async () => {
    const all = live.data.events?.[RUN_ID] ?? [];
    const before = upTo(all, (e) => e.type === "stage.done" && e.stage === "select");
    const { api } = await openScenario(live, { events: before });
    fireEvent.click((await screen.findAllByRole("button", { name: /Open source$/ }))[1]);
    const dialog = await screen.findByRole("dialog");
    const chosen = () => dialog.querySelector('[aria-current="true"]')?.getAttribute("data-chunk");
    await vi.waitFor(() => expect(chosen()).toBeTruthy());
    fireEvent.keyDown(dialog, { key: "ArrowDown" });
    const picked = chosen();
    await play(RUN_ID, [all[before.length]]);
    await vi.waitFor(() => expect(callsTo(api, "source")).toHaveLength(2));
    expect(chosen()).toBe(picked);
  });
});

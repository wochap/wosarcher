import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { cancelled } from "../../test/fixtures/cancelled";
import { failure } from "../../test/fixtures/failure";
import { RUN_ID } from "../../test/fixtures/sample";
import { openScenario } from "../../test/scenario";

const press = (name: string) =>
  act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });

describe("failed run", () => {
  it("shows the failed stage, the error, and Retry from Score", async () => {
    const { api } = await openScenario(failure);
    expect(screen.getByText("Failed")).toBeTruthy();
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Run failed at Score");
    expect(alert.textContent).toContain("CUDA out of memory");
    expect(alert.textContent).toContain("Plan through prefilter are cached.");
    expect(screen.getByRole("button", { name: "Help: Retry from Score" })).toBeTruthy();
    await press("Retry from Score");
    expect(callsTo(api, "forkRun")).toEqual([[RUN_ID, { from: "score" }]]);
    expect(window.location.hash).toBe("#/live/r_new1");
  });

  it("retries on the cloud profile", async () => {
    const { api } = await openScenario(failure);
    await press("Use cloud profile");
    expect(callsTo(api, "forkRun")).toEqual([[RUN_ID, { from: "score", profile: "cloud" }]]);
  });

  it("hides Use cloud profile without a cloud profile", async () => {
    const api = fakeApi(failure.data);
    api.data.profiles = api.data.profiles.filter((p) => p.name !== "cloud");
    await openScenario(failure, { api });
    await act(async () => {});
    expect(screen.queryByRole("button", { name: "Use cloud profile" })).toBeNull();
  });

  it("reruns with POST /api/runs/{id}/rerun", async () => {
    const { api } = await openScenario(failure);
    await press("Rerun");
    expect(callsTo(api, "rerunRun")).toEqual([[RUN_ID]]);
    expect(window.location.hash).toBe("#/live/r_new1");
  });

  it("shows an interrupted run as stopped without a final event", async () => {
    const api = fakeApi(failure.data);
    api.data.runs[0] = { ...api.data.runs[0], status: "interrupted" };
    const events = (failure.data.events?.[RUN_ID] ?? []).slice(0, -2);
    await openScenario(failure, { api, events });
    expect(await screen.findByText("Interrupted")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain(
      "The run stopped without a final event.",
    );
    expect(screen.getByRole("button", { name: "Retry from Score" })).toBeTruthy();
  });
});

describe("cancelled run", () => {
  it("names the stage, marks unfetched sources, and explains the empty panels", async () => {
    await openScenario(cancelled);
    expect(screen.getByText("Cancelled")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch(
      /^Cancelled at Fetch after \d+:\d\d\. Completed stages are kept; nothing was written\.$/,
    );
    expect(screen.getAllByText("not fetched").length).toBeGreaterThan(0);
    expect(screen.getByText("Cancelled before scoring.")).toBeTruthy();
    expect(screen.getByText("Cancelled before the write stage. Nothing was written.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Rerun" })).toBeTruthy();
  });
});

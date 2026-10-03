import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fakeApi } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";
import { newestActive } from "./App";

describe("App", () => {
  it("renders the shell and the current screen", async () => {
    renderApp({ hash: "#/new" });
    expect(await screen.findByRole("heading", { name: "New research run" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeTruthy();
  });

  it("follows the newest running run at start and opens it with Alt+2", async () => {
    const api = fakeApi();
    api.data.runs = [
      { ...api.data.runs[1], run_id: "r_old", status: "running", created: "2026-10-01T00:00:00Z" },
      { ...api.data.runs[1], run_id: "r_new", status: "queued", created: "2026-10-03T00:00:00Z" },
      { ...api.data.runs[1], run_id: "r_done", status: "done", created: "2026-10-04T00:00:00Z" },
    ];
    expect(newestActive(api.data.runs)).toBe("r_new");
    renderApp({ api });
    await screen.findByRole("heading", { name: "New research run" });
    await waitFor(() => expect(api.calls.some((c) => c.method === "listRuns")).toBe(true));
    await act(async () => {});
    fireEvent.keyDown(window, { code: "Digit2", key: "2", altKey: true });
    await waitFor(() => expect(window.location.hash).toBe("#/live/r_new"));
    expect(await screen.findByRole("heading", { name: "Live run" })).toBeTruthy();
  });
});

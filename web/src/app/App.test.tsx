import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
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
    expect(await screen.findByText("r_new")).toBeTruthy();
  });

  it("follows the running run after signing in", async () => {
    const api = fakeApi();
    api.data.runs = [{ ...api.data.runs[1], run_id: "r_live", status: "running" }];
    let signedIn = false;
    renderApp({
      hash: "#/new",
      api,
      wrap: (fake, unauthorized) => ({
        ...fake,
        getSession: async () => {
          if (signedIn) return fake.data.session;
          unauthorized();
          throw new ApiError(401, "unauthenticated", "sign in");
        },
        login: async (password) => {
          signedIn = true;
          return fake.login(password);
        },
      }),
    });
    fireEvent.change(await screen.findByLabelText("Password"), { target: { value: "pw" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    });
    const nav = screen.getByRole("navigation", { name: "Main" });
    await waitFor(() =>
      expect(
        within(nav)
          .getByRole("button", { name: /Live run/ })
          .querySelector('[data-tone="live"]'),
      ).toBeTruthy(),
    );
    fireEvent.keyDown(window, { code: "Digit2", key: "2", altKey: true });
    await waitFor(() => expect(window.location.hash).toBe("#/live/r_live"));
    expect(screen.queryByRole("heading", { name: "No run in progress" })).toBeNull();
  });
});

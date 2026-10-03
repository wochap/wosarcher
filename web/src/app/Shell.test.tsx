import { act, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ev } from "../test/events";
import { FakeWebSocket } from "../test/FakeWebSocket";
import { fakeApi } from "../test/fakeApi";
import { renderApp } from "../test/renderApp";

afterEach(() => vi.unstubAllGlobals());

const nav = () => screen.getByRole("navigation", { name: "Main" });
const current = () =>
  within(nav())
    .getAllByRole("button")
    .filter((b) => b.getAttribute("aria-current") === "page");

describe("Shell", () => {
  it("marks only the current screen's item", async () => {
    renderApp({ hash: "#/settings" });
    await screen.findByRole("heading", { name: "Settings" });
    expect(current().map((b) => b.textContent)).toEqual(["SettingsAlt 4"]);
  });

  it("highlights Live run on the Report screen", async () => {
    renderApp({ hash: "#/runs/r_7f3a" });
    await screen.findByRole("heading", { name: "Report" });
    expect(current()).toHaveLength(1);
    expect(current()[0].textContent).toContain("Live run");
  });

  it("shows the live dot while the followed run runs and the warn dot after a slow check", async () => {
    renderApp({ hash: "#/settings" });
    await screen.findByText("Slow · 1,840 ms · probe over 1000 ms");
    const socket = FakeWebSocket.last();
    act(() => {
      socket.open();
      socket.emit(
        ev(
          1,
          "run.started",
          { query: "q", profile: "p", parent_run_id: null, version: 1, until: null },
          null,
          "r_8c21",
        ),
      );
    });
    const live = within(nav()).getByRole("button", { name: /Live run/ });
    expect(live.querySelector('[data-tone="live"]')).toBeTruthy();
    const settings = within(nav()).getByRole("button", { name: /Settings/ });
    expect(settings.querySelector('[data-tone="warn"]')).toBeTruthy();
  });

  it("names the product wosarcher and never Sift", async () => {
    const { container } = renderApp({ hash: "#/settings" });
    await screen.findByRole("heading", { name: "Settings" });
    expect(within(nav()).getByText("wosarcher")).toBeTruthy();
    expect(container.textContent).not.toContain("Sift");
  });

  it("shows the phone top bar with labelled buttons below 720px", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("max-width"),
      addEventListener() {},
      removeEventListener() {},
    }));
    renderApp({ hash: "#/history", api: fakeApi() });
    await screen.findByRole("heading", { name: "Run history" });
    for (const label of ["New run", "Live run", "History", "Settings"]) {
      expect(within(nav()).getByRole("button", { name: label })).toBeTruthy();
    }
    expect(within(nav()).queryByText("Alt 1")).toBeNull();
  });
});

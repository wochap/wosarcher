import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { finished } from "../test/fixtures/finished";
import { QUERY } from "../test/fixtures/sample";
import { renderApp } from "../test/renderApp";
import { openScenario } from "../test/scenario";
import { topOverlay } from "./keys";

describe("keys", () => {
  it("switches screens with Alt+1..4 by physical key", async () => {
    renderApp({ hash: "#/new" });
    await screen.findByRole("heading", { name: "New research run" });
    fireEvent.keyDown(window, { code: "Digit3", key: "£", altKey: true });
    expect(await screen.findByRole("heading", { name: "Run history" })).toBeTruthy();
    fireEvent.keyDown(window, { code: "Digit4", key: "4", altKey: true });
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeTruthy();
  });

  it("focuses the History search with / outside a text field", async () => {
    renderApp({ hash: "#/history" });
    const search = await screen.findByLabelText("Search runs");
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(search);
  });

  it("does nothing while locked", async () => {
    renderApp({
      hash: "#/history",
      wrap: (api, unauthorized) => ({
        ...api,
        getSession: async () => {
          unauthorized();
          throw new Error("401");
        },
      }),
    });
    await screen.findByRole("heading", { name: "Sign in" });
    fireEvent.keyDown(window, { code: "Digit4", key: "4", altKey: true });
    await waitFor(() => expect(window.location.hash).toBe("#/history"));
  });

  it("closes the help tooltip before the dialog", async () => {
    await openScenario(finished);
    await screen.findByRole("heading", { level: 1, name: QUERY });
    fireEvent.click(screen.getByRole("button", { name: "Rewrite" }));
    const dialog = screen.getByRole("dialog", { name: "Rewrite report" });
    fireEvent.focus(within(dialog).getByRole("button", { name: "Help: Tone" }));
    expect(screen.getByRole("tooltip").textContent).toContain("Tone");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes help first, then the confirmation, the form dialog, and the tooltip", () => {
    const help = { kind: "help" as const, close: vi.fn() };
    const tooltip = { kind: "tooltip" as const, close: vi.fn() };
    const form = { kind: "dialog" as const, close: vi.fn() };
    const confirm = { kind: "alertdialog" as const, close: vi.fn() };
    expect(topOverlay([tooltip, confirm, help, form])).toBe(help);
    expect(topOverlay([tooltip, confirm, form])).toBe(confirm);
    expect(topOverlay([tooltip, form])).toBe(form);
    expect(topOverlay([tooltip])).toBe(tooltip);
    expect(topOverlay([])).toBeUndefined();
  });
});

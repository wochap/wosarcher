import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/renderApp";
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

  it("closes the confirmation before the form dialog before the tooltip", () => {
    const tooltip = { kind: "tooltip" as const, close: vi.fn() };
    const form = { kind: "dialog" as const, close: vi.fn() };
    const confirm = { kind: "alertdialog" as const, close: vi.fn() };
    expect(topOverlay([tooltip, confirm, form])).toBe(confirm);
    expect(topOverlay([tooltip, form])).toBe(form);
    expect(topOverlay([tooltip])).toBe(tooltip);
    expect(topOverlay([])).toBeUndefined();
  });
});

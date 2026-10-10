import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ServerSettings } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

describe("RunSlots", () => {
  it("shows the slots in use (scenario settings)", async () => {
    renderApp({ hash: "#/settings", api: fakeApi() });
    expect(await screen.findByText("2 of 2 in use")).toBeTruthy();
    expect(screen.getByText("1 web · 1 CLI · 1 queued")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Run slots" })).toBeTruthy();
  });

  it("saves a raised limit and shows its bars", async () => {
    const api = fakeApi();
    const { container } = renderApp({ hash: "#/settings", api });
    const field = await screen.findByLabelText("Max concurrent runs");
    await act(async () => {
      fireEvent.change(field, { target: { value: "3" } });
    });
    const puts = callsTo(api, "putSettings") as [ServerSettings][];
    expect(puts.at(-1)?.[0].max_concurrent_runs).toBe(3);
    expect(screen.getByText("2 of 3 in use")).toBeTruthy();
    expect(container.querySelectorAll("[data-held]")).toHaveLength(3);
  });

  it("does not save 9", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    const field = await screen.findByLabelText("Max concurrent runs");
    await act(async () => {
      fireEvent.change(field, { target: { value: "9" } });
    });
    expect(callsTo(api, "putSettings")).toHaveLength(0);
  });

  it("notes that running runs keep going at limit 1", async () => {
    renderApp({ hash: "#/settings", api: fakeApi() });
    const field = await screen.findByLabelText("Max concurrent runs");
    await act(async () => {
      fireEvent.change(field, { target: { value: "1" } });
    });
    expect(
      screen.getByText(
        "Runs that are already going keep going. The lower limit applies as they finish.",
      ),
    ).toBeTruthy();
  });
});

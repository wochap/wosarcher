import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ServerSettings } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

describe("RunDefaults", () => {
  it("autosaves a block list and shows Saved", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    const block = await screen.findByLabelText("Block domains");
    await act(async () => {
      fireEvent.change(block, { target: { value: "pinterest.com" } });
      fireEvent.keyDown(block, { key: "Enter" });
    });
    const puts = callsTo(api, "putSettings") as [ServerSettings][];
    expect(puts.at(-1)?.[0].domains).toEqual({ allow: [], block: ["pinterest.com"] });
    expect(puts.at(-1)?.[0].writing.words).toBe(1200);
    expect(screen.getByText("Saved")).toBeTruthy();
  });

  it("autosaves the default format, and New run preselects it", async () => {
    const api = fakeApi();
    renderApp({ hash: "#/settings", api });
    const format = await screen.findByRole("radiogroup", { name: "Format" });
    expect(format.textContent).toBe("reportanswer");
    expect(
      screen.getByText("Preselects the Recipe on New run. Context is chosen per run."),
    ).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByLabelText("answer"));
    });
    const puts = callsTo(api, "putSettings") as [ServerSettings][];
    expect(puts.at(-1)?.[0].writing.format).toBe("answer");
    expect(screen.getByText("Saved")).toBeTruthy();
    await act(async () => {
      window.location.hash = "#/new";
    });
    fireEvent.click(await screen.findByRole("button", { name: /Options/ }));
    expect((screen.getByLabelText("answer") as HTMLInputElement).checked).toBe(true);
  });

  it("names the profiles that set their own lists", async () => {
    const api = fakeApi();
    api.data.profiles[0].block_domains = ["pinterest.com", "quora.com"];
    api.data.profiles[3].block_domains = ["facebook.com"];
    renderApp({ hash: "#/settings", api });
    expect(
      await screen.findByText(
        "The low-vram and nixos profiles set their own domain lists; runs on those profiles use them instead.",
      ),
    ).toBeTruthy();
  });

  it("has the Run defaults help and no overridden marks", async () => {
    const api = fakeApi();
    api.data.settings.domains.allow = ["gob.pe"];
    renderApp({ hash: "#/settings", api });
    expect(await screen.findByRole("button", { name: "Help: Run defaults" })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Remove gob.pe" })).toBeTruthy();
    expect(screen.queryByText("overridden")).toBeNull();
  });
});

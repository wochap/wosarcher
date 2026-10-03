import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

async function openOptions(api = fakeApi()) {
  renderApp({ hash: "#/new", api });
  fireEvent.click(await screen.findByRole("button", { name: /Options/ }));
  return api;
}

describe("OptionsPanel", () => {
  it("summarizes the options and offers the profiles from the server", async () => {
    await openOptions();
    const header = screen.getByRole("button", { name: /Options/ });
    expect(header.textContent).toContain(
      "report · both · low-vram · Analytical · 1200 words · English · [1] Numeric",
    );
    expect((screen.getByLabelText("low-vram") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByLabelText("cloud")).toBeTruthy();
  });

  it("marks one override and resets it", async () => {
    await openOptions();
    const words = screen.getByLabelText("Target length");
    fireEvent.change(words, { target: { value: "600" } });
    fireEvent.blur(words);
    expect(screen.getByText("overridden")).toBeTruthy();
    expect(screen.getByText("default: 1200 words")).toBeTruthy();
    expect(screen.getByText("1 overridden")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Reset all to defaults/ }));
    expect(screen.queryByText("overridden")).toBeNull();
  });

  it("follows a changed default when the field is not overridden", async () => {
    const api = await openOptions();
    api.data.settings.writing.tone = "formal";
    await act(async () => {
      window.location.hash = "#/settings";
    });
    await act(async () => {
      window.location.hash = "#/new";
    });
    fireEvent.click(await screen.findByRole("button", { name: /Options/ }));
    expect((screen.getByLabelText("Formal") as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByText("overridden")).toBeNull();
  });
});

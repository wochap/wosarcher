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
      "report · both · low-vram · Analytical · 1200 words · English · [1] Numeric · APA",
    );
    const profile = screen.getByLabelText("Profile") as HTMLSelectElement;
    expect(profile.value).toBe("low-vram");
    expect([...profile.options].map((o) => o.textContent)).toEqual([
      "low-vram",
      "workstation",
      "cloud",
      "nixos  (user profile)",
    ]);
  });

  it("lists report before context", async () => {
    await openOptions();
    const recipe = screen.getByRole("radiogroup", { name: "Recipe" });
    expect(recipe.textContent).toBe("reportcontext");
  });

  it("shows the selected profile's description", async () => {
    await openOptions();
    expect(screen.getByText("Models take turns on one small GPU; slower, fits 8 GB.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "nixos" } });
    expect(screen.queryByText("Models take turns on one small GPU; slower, fits 8 GB.")).toBeNull();
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "cloud" } });
    expect(screen.getByText("Hosted APIs only; needs API keys.")).toBeTruthy();
  });

  it("has one help button per Run row", async () => {
    await openOptions();
    for (const label of ["Recipe", "Sources", "Profile"])
      expect(screen.getAllByRole("button", { name: `Help: ${label}` })).toHaveLength(1);
  });

  it("marks one override and resets it", async () => {
    await openOptions();
    const words = screen.getByLabelText("Length (words)");
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
    expect((screen.getByLabelText("Tone") as HTMLSelectElement).value).toBe("formal");
    expect(screen.queryByText("overridden")).toBeNull();
  });
});

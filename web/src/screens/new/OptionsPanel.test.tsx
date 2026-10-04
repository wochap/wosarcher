import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { RunCreate } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

async function openOptions(api = fakeApi()) {
  renderApp({ hash: "#/new", api });
  fireEvent.click(await screen.findByRole("button", { name: /Options/ }));
  return api;
}

const header = () => screen.getByRole("button", { name: /Options/ }).textContent;

async function start(api: ReturnType<typeof fakeApi>) {
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: "q" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Run research" }));
  });
  return callsTo(api, "createRun").at(-1)?.[0] as RunCreate;
}

function setWords(value: string) {
  const words = screen.getByLabelText("Length (words)");
  fireEvent.change(words, { target: { value } });
  fireEvent.blur(words);
}

beforeEach(() => localStorage.clear());

describe("OptionsPanel", () => {
  it("summarizes the options and offers the profiles from the server", async () => {
    await openOptions();
    expect(header()).toContain("Standard · report · both · low-vram · 1200 words · Analytical");
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

describe("Depth", () => {
  it("sends a picked preset with no research or words", async () => {
    const api = await openOptions();
    fireEvent.click(screen.getByLabelText("Deep"));
    expect(header()).toContain("Deep · report · both · low-vram · 2000 words · Analytical");
    expect(screen.getByText("More searches and sources, longer report.")).toBeTruthy();
    expect(screen.getByText("~60 pages · 1 round · ~2 LLM calls")).toBeTruthy();
    const request = await start(api);
    expect(request.depth).toBe("deep");
    expect(request.research).toBeUndefined();
    expect(request.writing).toBeUndefined();
  });

  it("switches to Custom when an Advanced value is edited", async () => {
    const api = await openOptions();
    fireEvent.click(screen.getByLabelText("Deep"));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    fireEvent.change(screen.getByLabelText("Max pages"), { target: { value: "80" } });
    expect((screen.getByLabelText("Custom") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Sub-queries") as HTMLInputElement).value).toBe("5");
    expect(screen.getByText("Your Custom values, saved in this browser.")).toBeTruthy();
    const request = await start(api);
    expect(request.depth).toBe("custom");
    expect(request.research).toEqual({
      sub_queries: 5,
      results_per_query: 10,
      max_pages: 80,
      passages_per_query: 10,
      context_tokens: 24000,
    });
    expect(request.writing).toEqual({ words: 2000 });
  });

  it("shows the context the model window allows", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Exhaustive"));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    expect(screen.getByText("32,000 → 24,768 (model window)")).toBeTruthy();
    expect(screen.getByText(/context 32k → 25k \(model window\)$/)).toBeTruthy();
  });

  it("keeps Rounds at one", async () => {
    await openOptions();
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    const rounds = screen.getByLabelText("Rounds") as HTMLInputElement;
    expect(rounds.value).toBe("1");
    expect(rounds.disabled).toBe(true);
    expect(screen.getByText("This server runs 1 round only.")).toBeTruthy();
  });

  it("lets Length follow the depth until it is edited", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Deep"));
    const words = screen.getByLabelText("Length (words)") as HTMLInputElement;
    expect(words.value).toBe("2000");
    expect(screen.getByText("· set by Deep")).toBeTruthy();
    setWords("800");
    fireEvent.click(screen.getByLabelText("Quick"));
    expect((screen.getByLabelText("Length (words)") as HTMLInputElement).value).toBe("800");
    expect(screen.getByText("Quick default: 600 words")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Depth default" })).toBeTruthy();
  });

  it("remembers the Custom values", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Custom"));
    fireEvent.change(screen.getByLabelText("Sub-queries"), { target: { value: "6" } });
    cleanup();
    await openOptions();
    fireEvent.click(screen.getByLabelText("Custom"));
    expect((screen.getByLabelText("Sub-queries") as HTMLInputElement).value).toBe("6");
  });
});

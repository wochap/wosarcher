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

  it("lists report, answer, then context", async () => {
    await openOptions();
    const recipe = screen.getByRole("radiogroup", { name: "Recipe" });
    expect(recipe.textContent).toBe("reportanswercontext");
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
    expect(screen.getByText("Several research rounds that follow up on gaps.")).toBeTruthy();
    expect(screen.getByText("~60 pages · 3 rounds · ~4 LLM calls")).toBeTruthy();
    const request = await start(api);
    expect(request.depth).toBe("deep");
    expect(request.research).toBeUndefined();
    expect(request.writing).toEqual({ format: "report" });
  });

  it("switches to Custom when an Advanced value is edited", async () => {
    const api = await openOptions();
    fireEvent.click(screen.getByLabelText("Deep"));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    fireEvent.change(screen.getByLabelText("Max pages"), { target: { value: "80" } });
    expect((screen.getByLabelText("Custom") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Sub-queries") as HTMLInputElement).value).toBe("6");
    expect(screen.getByText("Your Custom values, saved in this browser.")).toBeTruthy();
    const request = await start(api);
    expect(request.depth).toBe("custom");
    expect(request.research).toEqual({
      sub_queries: 6,
      results_per_query: 10,
      max_pages: 80,
      passages_per_query: 10,
      context_tokens: "auto",
      gap_context_tokens: 4000,
      rounds: 3,
      queries_per_round: 3,
    });
    expect(request.writing).toEqual({ words: 2000, format: "report" });
  });

  it("shows Auto context with its effective budget", async () => {
    const api = fakeApi();
    api.data.profiles[0] = { ...api.data.profiles[0], context_window: 131072 };
    await openOptions(api);
    fireEvent.click(screen.getByLabelText("Deep"));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    expect((screen.getByLabelText("Context tokens") as HTMLInputElement).value).toBe("");
    expect(screen.getByText("Auto · 125,072")).toBeTruthy();
    expect(screen.getByText("~60 pages · 3 rounds · ~4 LLM calls")).toBeTruthy();
    expect(screen.queryByText(/model window/)).toBeNull();
  });

  it("shows the context the model window allows", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Exhaustive"));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    fireEvent.change(screen.getByLabelText("Context tokens"), { target: { value: "32000" } });
    expect(screen.getByText("32,000 → 24,768 (model window)")).toBeTruthy();
    expect(screen.getByText(/context 32k → 25k \(model window\)$/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Context tokens"), { target: { value: "" } });
    expect(screen.getByText("Auto · 24,768")).toBeTruthy();
    expect(screen.queryByText(/context 32k/)).toBeNull();
  });

  it("shows Auto gap context and sends it", async () => {
    const api = fakeApi();
    api.data.profiles[0] = { ...api.data.profiles[0], context_window: 1000000 };
    await openOptions(api);
    fireEvent.click(screen.getByLabelText("Deep"));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    const gap = screen.getByLabelText("Gap context tokens") as HTMLInputElement;
    expect(gap.value).toBe("4000");
    fireEvent.change(gap, { target: { value: "" } });
    expect((screen.getByLabelText("Custom") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Rounds") as HTMLInputElement).value).toBe("3");
    expect(screen.getByText("Auto · 997,232")).toBeTruthy();
    const request = await start(api);
    expect(request.research?.gap_context_tokens).toBe("auto");
    expect(Object.keys(request.research ?? {})).toHaveLength(8);
  });

  it("locks Gap context tokens and Follow-ups per round at one round", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Quick"));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    expect((screen.getByLabelText("Gap context tokens") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Follow-ups per round") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getAllByText("Used between rounds; needs 2+ rounds.")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Help: Gap context tokens" })).toBeTruthy();
  });

  it("edits Rounds, and keeps files-only runs at one round", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Deep"));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    const rounds = screen.getByLabelText("Rounds") as HTMLInputElement;
    expect(rounds.value).toBe("3");
    expect(rounds.disabled).toBe(false);
    fireEvent.click(screen.getByLabelText("files"));
    expect(rounds.value).toBe("1");
    expect(rounds.disabled).toBe(true);
    expect(screen.getByText("Files-only runs use 1 round.")).toBeTruthy();
    expect(screen.getByText(/· 1 round ·/)).toBeTruthy();
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

  it("starts the domain rows from the profile's lists, else the global defaults", async () => {
    const api = fakeApi();
    api.data.profiles[0].allow_domains = ["gob.pe", "sbs.gob.pe"];
    api.data.profiles[0].block_domains = null;
    api.data.settings.domains.block = ["facebook.com"];
    await openOptions(api);
    expect(screen.getByRole("button", { name: "Remove gob.pe" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remove sbs.gob.pe" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remove facebook.com" })).toBeTruthy();
    expect(header()).not.toContain("overridden");
    expect((await start(api)).domains).toBeUndefined();
  });

  it("sends an overridden Allow list for one run", async () => {
    const api = await openOptions();
    const allow = screen.getByLabelText("Allow domains");
    fireEvent.change(allow, { target: { value: "gob.pe pj.gob.pe" } });
    fireEvent.blur(allow);
    expect(screen.getByText("default: none")).toBeTruthy();
    expect(header()).toContain("1 overridden");
    expect((await start(api)).domains).toEqual({ allow: ["gob.pe", "pj.gob.pe"] });
  });

  it("sends an empty list when a default list is cleared", async () => {
    const api = fakeApi();
    api.data.settings.domains.block = ["facebook.com"];
    await openOptions(api);
    fireEvent.click(screen.getByRole("button", { name: "Remove facebook.com" }));
    expect(screen.getByText("default: facebook.com")).toBeTruthy();
    expect(screen.getByText("overridden")).toBeTruthy();
    expect((await start(api)).domains).toEqual({ block: [] });
  });

  it("follows the selected profile's lists while the rows are not edited", async () => {
    const api = fakeApi();
    api.data.profiles[1].block_domains = ["quora.com"];
    api.data.settings.domains.allow = ["gob.pe"];
    await openOptions(api);
    expect(screen.queryByRole("button", { name: "Remove quora.com" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "workstation" } });
    expect(screen.getByRole("button", { name: "Remove quora.com" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remove gob.pe" })).toBeTruthy();
    expect(screen.queryByText("overridden")).toBeNull();
  });

  it("ends the Run group with the domain rows", async () => {
    await openOptions();
    const labels = ["Recipe", "Sources", "Profile", "Allow domains", "Block domains"];
    const found = labels.map((label) => screen.getAllByText(label)[0]);
    for (let n = 1; n < found.length; n++) {
      expect(
        found[n - 1].compareDocumentPosition(found[n]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });
});

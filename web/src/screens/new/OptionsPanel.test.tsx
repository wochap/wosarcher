import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { DepthInfo, RunCreate } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

async function openOptions(api = fakeApi()) {
  renderApp({ hash: "#/new", api });
  fireEvent.click(await screen.findByRole("button", { name: /Options/ }));
  return api;
}

const header = () => screen.getByRole("button", { name: /Options/ }).textContent;
/** The Advanced toggles: Depth's first, then the profile's. */
const depthAdvanced = () =>
  fireEvent.click(screen.getAllByRole("button", { name: /^Advanced/ })[0]);
const profileAdvanced = () =>
  fireEvent.click(screen.getAllByRole("button", { name: /^Advanced/ })[1]);
const profileGroup = () => screen.getByRole("radiogroup", { name: "Profile" });
const pickProfile = (name: string) => fireEvent.click(within(profileGroup()).getByLabelText(name));
const field = (label: string) =>
  screen.getByLabelText(label, { selector: "input, select" }) as HTMLInputElement;

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

/** A user depth preset with wide-ish values. */
const userDepth = (name: string): DepthInfo => ({
  name,
  description: `Your preset ${name}.`,
  source: "user",
  managed: false,
  values: {
    sub_queries: 10,
    results_per_query: 8,
    max_pages: 90,
    passages_per_query: 8,
    rounds: 1,
    queries_per_round: 3,
    words: null,
  },
});

describe("OptionsPanel", () => {
  it("summarizes the options and offers the profiles from the server", async () => {
    await openOptions();
    expect(header()).toContain("Standard · report · both · low-vram · 1200 words · Analytical");
    expect(profileGroup().textContent).toBe("low-vramworkstationnixos");
    expect((within(profileGroup()).getByLabelText("low-vram") as HTMLInputElement).checked).toBe(
      true,
    );
    expect(document.getElementById("opt-profile")).toBeNull();
  });

  it("lists report, answer, then context", async () => {
    await openOptions();
    const recipe = screen.getByRole("radiogroup", { name: "Recipe" });
    expect(recipe.textContent).toBe("reportanswercontext");
  });

  it("shows the selected profile's description", async () => {
    await openOptions();
    expect(screen.getByText("Models take turns on one small GPU; slower, fits 8 GB.")).toBeTruthy();
    pickProfile("nixos");
    expect(screen.queryByText("Models take turns on one small GPU; slower, fits 8 GB.")).toBeNull();
    pickProfile("workstation");
    expect(screen.getByText("One GPU fits all models; models stay loaded.")).toBeTruthy();
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
    depthAdvanced();
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
      rounds: 3,
      queries_per_round: 3,
    });
    expect(request.writing).toEqual({ words: 2000, format: "report" });
  });

  it("Pick a user preset: lists it before Custom and sends its name", async () => {
    const api = fakeApi();
    api.data.depths.push({
      name: "wide",
      description: "Many sub-queries, one round.",
      source: "user",
      values: {
        sub_queries: 10,
        results_per_query: 8,
        max_pages: 90,
        passages_per_query: 8,
        rounds: 1,
        queries_per_round: 3,
        words: null,
      },
    });
    await openOptions(api);
    const depth = screen.getByRole("radiogroup", { name: "Depth" });
    expect(depth.textContent).toBe("QuickStandardDeepExhaustivewideCustom");
    fireEvent.click(screen.getByLabelText("wide"));
    expect(screen.getByText("Many sub-queries, one round.")).toBeTruthy();
    depthAdvanced();
    expect(screen.getByText("wide preset. Edit any value to switch to Custom.")).toBeTruthy();
    expect(field("Sub-queries").value).toBe("10");
    expect(field("Max pages").value).toBe("90");
    expect(header()).toContain("wide · report");
    const request = await start(api);
    expect(request.depth).toBe("wide");
    expect(request.research).toBeUndefined();
  });

  it("Many user presets: the extras go into a More… select", async () => {
    const api = fakeApi();
    for (const name of ["lit-review", "news-scan", "survey-fast", "wide"])
      api.data.depths.push(userDepth(name));
    await openOptions(api);
    const more = screen.getByLabelText("More depth presets") as HTMLSelectElement;
    expect([...more.options].map((o) => o.textContent)).toEqual(["More…", "survey-fast", "wide"]);
    expect(screen.getByLabelText("lit-review")).toBeTruthy();
    expect(screen.getByLabelText("news-scan")).toBeTruthy();
    fireEvent.change(more, { target: { value: "wide" } });
    expect(more.value).toBe("wide");
    expect([...more.options].map((o) => o.textContent)).toEqual(["survey-fast", "wide"]);
    const radio = more.parentElement?.querySelector("input") as HTMLInputElement;
    expect(radio.checked).toBe(true);
    expect(header()).toContain("wide · report");
  });

  it("Save to a user preset: sends PUT and selects the preset", async () => {
    const api = fakeApi();
    api.data.depths.push(userDepth("wide"));
    await openOptions(api);
    fireEvent.click(screen.getByLabelText("wide"));
    depthAdvanced();
    fireEvent.change(field("Max pages"), { target: { value: "120" } });
    expect((screen.getByLabelText("Custom") as HTMLInputElement).checked).toBe(true);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save to wide" }));
    });
    const [[name, body]] = callsTo(api, "replaceDepth") as [string, { values: object }][];
    expect(name).toBe("wide");
    expect(body.values).toMatchObject({ max_pages: 120, sub_queries: 10, words: 1200 });
    expect((screen.getByLabelText("wide") as HTMLInputElement).checked).toBe(true);
    expect(field("Max pages").value).toBe("120");
    expect(screen.getByText("Saved depth “wide”")).toBeTruthy();
  });

  it("Managed preset edited: no Save to, a lock note instead", async () => {
    const api = fakeApi();
    api.data.depths.push({ ...userDepth("lit-review"), managed: true });
    await openOptions(api);
    fireEvent.click(screen.getByLabelText("lit-review"));
    depthAdvanced();
    expect(screen.getByText("Managed by NixOS config · read-only")).toBeTruthy();
    fireEvent.change(field("Max pages"), { target: { value: "120" } });
    expect(screen.getByText("lit-review is managed by NixOS config")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save depth as…" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Save to/ })).toBeNull();
  });

  it("built-in presets show no action row", async () => {
    await openOptions();
    depthAdvanced();
    expect(screen.queryByRole("button", { name: /^Delete|^Save/ })).toBeNull();
  });

  it("Save a depth: posts the values, Length, and description, then selects it", async () => {
    const api = await openOptions();
    fireEvent.click(screen.getByLabelText("Custom"));
    fireEvent.change(field("Sub-queries"), { target: { value: "10" } });
    setWords("1500");
    fireEvent.click(screen.getByRole("button", { name: "Save depth as…" }));
    expect(screen.getByText("Length")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "wide-short" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save depth" }));
    });
    const [[body]] = callsTo(api, "saveDepth") as [{ description: string; values: object }][];
    expect(body.description).toBe("Your preset: 10 sub-queries, 1 round, 1,500 words.");
    expect(body.values).toMatchObject({ sub_queries: 10, rounds: 1, words: 1500 });
    expect((screen.getByLabelText("wide-short") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("Saved depth “wide-short”")).toBeTruthy();
  });

  it("Name taken: names the clash and sends nothing", async () => {
    const api = fakeApi();
    api.data.depths.push(userDepth("wide"));
    await openOptions(api);
    fireEvent.click(screen.getByLabelText("Custom"));
    fireEvent.click(screen.getByRole("button", { name: "Save depth as…" }));
    fireEvent.click(screen.getByRole("button", { name: "Save depth" }));
    expect(screen.getByText("Enter a name.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Wide" } });
    expect(screen.getByText("A depth named “Wide” already exists.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "_x" } });
    expect(screen.getByText("Start with a letter or digit.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Deep" } });
    expect(screen.getByText("“Deep” is reserved for a built-in depth.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save depth" }));
    expect(callsTo(api, "saveDepth")).toEqual([]);
  });

  it("shows the server's refusal as the name error", async () => {
    const api = fakeApi();
    api.saveDepth = async () => {
      throw new ApiError(409, "name_taken", "a depth preset named 'x' already exists");
    };
    await openOptions(api);
    fireEvent.click(screen.getByLabelText("Custom"));
    fireEvent.click(screen.getByRole("button", { name: "Save depth as…" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "x" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save depth" }));
    });
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText("a depth preset named 'x' already exists")).toBeTruthy();
  });

  it("Delete the selected preset: confirms, deletes, and switches to Standard", async () => {
    const api = fakeApi();
    api.data.depths.push(userDepth("wide"));
    await openOptions(api);
    fireEvent.click(screen.getByLabelText("wide"));
    depthAdvanced();
    fireEvent.click(screen.getByRole("button", { name: "Delete wide" }));
    expect(screen.getByText("Delete depth “wide”?")).toBeTruthy();
    expect(
      screen.getByText(
        "Runs that used it keep the values they ran with. Depth switches to Standard. This can’t be undone.",
      ),
    ).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete depth" }));
    });
    expect(callsTo(api, "deleteDepth")).toEqual([["wide"]]);
    expect((screen.getByLabelText("Standard") as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByLabelText("wide")).toBeNull();
    expect(screen.getByText("Deleted depth “wide”")).toBeTruthy();
  });

  it("No budgets in Depth: Advanced has the six research values only", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Deep"));
    depthAdvanced();
    const grid = screen.getByText("Deep preset. Edit any value to switch to Custom.")
      .parentElement as HTMLElement;
    const labels = [...grid.querySelectorAll("label")].map((l) => l.textContent);
    expect(labels).toEqual([
      "Sub-queries",
      "Results per query",
      "Max pages",
      "Rounds",
      "Follow-ups per round",
      "Passages per query",
    ]);
    expect(screen.queryByLabelText("Context tokens")).toBeNull();
    expect(screen.queryByLabelText("Model")).toBeNull();
    expect(screen.queryByLabelText("Write thinking")).toBeNull();
    expect(screen.getByText("~60 pages · 3 rounds · ~4 LLM calls")).toBeTruthy();
  });

  it("locks Follow-ups per round at one round", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Quick"));
    depthAdvanced();
    expect(field("Follow-ups per round").disabled).toBe(true);
    expect(screen.getAllByText("Used between rounds; needs 2+ rounds.")).toHaveLength(1);
  });

  it("edits Rounds, and keeps files-only runs at one round", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Deep"));
    depthAdvanced();
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
    pickProfile("workstation");
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

describe("Profile advanced values", () => {
  it("shows the profile's values with single entries locked", async () => {
    await openOptions();
    expect(screen.getAllByRole("button", { name: /^Advanced/ })[0].textContent).toBe(
      "Advanced· Standard values",
    );
    profileAdvanced();
    expect(screen.getAllByRole("button", { name: /^Advanced/ })[1].textContent).toBe(
      "Advanced· low-vram values",
    );
    expect(
      screen.getByText("Values from the low-vram profile. Edits apply to this run only."),
    ).toBeTruthy();
    for (const label of ["Search", "Fetch"]) expect(field(label).disabled).toBe(true);
    expect(screen.getAllByText("Only one configured.")).toHaveLength(2);
    expect(field("Scorer").value).toBe("rerank");
    expect(field("Model").value).toBe("qwen3-14b");
    expect(field("Context window").value).toBe("32768");
    expect(field("Max output").value).toBe("8192");
    expect(field("Context tokens").value).toBe("");
    expect(screen.getByText("Auto · 28,368")).toBeTruthy();
    expect(field("Gap context tokens").value).toBe("4000");
    expect(screen.queryByText("overridden")).toBeNull();
  });

  it("Three edits: marks them, clamps the budget, and sends only them", async () => {
    const api = await openOptions();
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "jev-strict" } });
    fireEvent.change(field("Write thinking"), { target: { value: "high" } });
    fireEvent.change(field("Context tokens"), { target: { value: "60000" } });
    expect(screen.getAllByRole("button", { name: /^Advanced/ })[1].textContent).toBe(
      "Advanced· 3 changed",
    );
    expect(screen.getAllByText("overridden")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Help: Overridden" })).toHaveLength(2);
    expect(screen.getByText("edited")).toBeTruthy();
    expect(screen.getByText("60,000 → 32,000 (model window)")).toBeTruthy();
    expect(
      screen.getByText("Changed for this run only; the low-vram profile itself is unchanged."),
    ).toBeTruthy();
    expect(header()).toContain("both · custom (low-vram) · 1200 words");
    const request = await start(api);
    expect(request.use).toEqual({ score: "jev-strict" });
    expect(request.llm).toEqual({ reasoning: { write: "high" }, context_tokens: 60000 });
  });

  it("LLM switch: takes the entry's default model and its limits", async () => {
    const api = await openOptions();
    profileAdvanced();
    fireEvent.change(field("Max output"), { target: { value: "4096" } });
    fireEvent.change(field("LLM"), { target: { value: "omniroute" } });
    expect(field("Model").value).toBe("research-smart");
    expect(field("Context window").value).toBe("1048576");
    expect(field("Max output").value).toBe("32768");
    expect(field("Plan thinking").value).toBe("high");
    expect(screen.getAllByText("overridden")).toHaveLength(1);
    await act(async () => {});
    expect(callsTo(api, "listModels").at(-1)).toEqual(["omniroute"]);
    const request = await start(api);
    expect(request.use).toEqual({ llm: "omniroute" });
    expect(request.llm).toBeUndefined();
  });

  it("notes the fallback limits of a model the entry does not list", async () => {
    await openOptions();
    pickProfile("nixos");
    profileAdvanced();
    expect(field("Model").value).toBe("qwen3-30b-a3b");
    expect(field("Context window").value).toBe("32768");
    expect(field("Max output").value).toBe("8192");
    expect(screen.getAllByText("Fallback: no limits set for this model.")).toHaveLength(2);
    expect(screen.getAllByText("from profile")).toHaveLength(1);
    expect(screen.queryByText("from entry")).toBeNull();
  });

  it("Profile tuning shown: the profile's model table over the entry's", async () => {
    const api = fakeApi();
    api.data.profiles.push({
      ...api.data.profiles[1],
      name: "tuned",
      models: [{ id: "qwen3-14b", reasoning: { write: "high" } }],
    });
    await openOptions(api);
    pickProfile("tuned");
    profileAdvanced();
    expect(field("Write thinking").value).toBe("high");
    expect(field("Context window").value).toBe("32768");
    const tagOf = (label: string) =>
      field(label).parentElement?.querySelector("span[data-edited]")?.textContent;
    expect(tagOf("Write thinking")).toBe("from profile");
    expect(tagOf("Context window")).toBe("from entry");
    expect(tagOf("Max output")).toBe("from entry");
    expect(tagOf("Plan thinking")).toBeUndefined();
  });

  it("Save edits into a profile: sends PATCH, reloads, and clears the edits", async () => {
    const api = await openOptions();
    pickProfile("workstation");
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "rerank" } });
    fireEvent.change(field("Write thinking"), { target: { value: "high" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save to workstation" }));
    });
    expect(callsTo(api, "updateProfile")).toEqual([
      ["workstation", { use: { score: "rerank" }, llm: { reasoning: { write: "high" } } }],
    ]);
    expect(screen.getAllByRole("button", { name: /^Advanced/ })[1].textContent).toBe(
      "Advanced· workstation values",
    );
    expect(screen.getByText("Saved profile “workstation”")).toBeTruthy();
  });

  it("Active profile not deletable", async () => {
    await openOptions();
    profileAdvanced();
    const remove = screen.getByRole("button", { name: "Delete low-vram" }) as HTMLButtonElement;
    expect(remove.disabled).toBe(true);
    expect(screen.getByText("The default profile can’t be deleted")).toBeTruthy();
  });

  it("Managed profile: read-only, saved only as a new profile", async () => {
    const api = fakeApi();
    api.data.profiles[1].managed = true;
    await openOptions(api);
    pickProfile("workstation");
    profileAdvanced();
    expect(screen.getByText("Managed by NixOS config · read-only")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Delete/ })).toBeNull();
    fireEvent.change(field("Scorer"), { target: { value: "rerank" } });
    expect(screen.getByText("workstation is managed by NixOS config")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save to workstation" })).toBeNull();
    expect(screen.getByRole("button", { name: "Save profile as…" })).toBeTruthy();
  });

  it("Save a profile: posts the edits from the selected profile and selects it", async () => {
    const api = await openOptions();
    pickProfile("workstation");
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "rerank" } });
    fireEvent.change(field("Write thinking"), { target: { value: "medium" } });
    fireEvent.change(field("Context tokens"), { target: { value: "120000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile as…" }));
    expect(
      screen.getByText(
        "Saves a new profile based on workstation, with your 3 edits. workstation itself is unchanged.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Model tuning for qwen3-14b")).toBeTruthy();
    expect(screen.getByText("plan none · gap none · write medium")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "cloud-rerank" } });
    fireEvent.change(screen.getByLabelText(/^Description/), {
      target: { value: "Hosted models with the local reranker." },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    });
    expect(callsTo(api, "saveProfile")).toEqual([
      [
        {
          name: "cloud-rerank",
          from: "workstation",
          description: "Hosted models with the local reranker.",
          use: { score: "rerank" },
          llm: { reasoning: { write: "medium" }, context_tokens: 120000 },
        },
      ],
    ]);
    expect(
      (within(profileGroup()).getByLabelText("cloud-rerank") as HTMLInputElement).checked,
    ).toBe(true);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Saved profile “cloud-rerank”")).toBeTruthy();
    expect(header()).not.toContain("custom (");
  });

  it("drops the limit edits when the model changes", async () => {
    const api = await openOptions();
    profileAdvanced();
    fireEvent.change(field("Context window"), { target: { value: "16384" } });
    fireEvent.change(field("Model"), { target: { value: "gemma-3-12b" } });
    expect(field("Context window").value).toBe("32768");
    expect(screen.getAllByText("Fallback: no limits set for this model.")).toHaveLength(2);
    expect((await start(api)).llm).toEqual({ model: "gemma-3-12b" });
  });

  it("Reset: removes every edit", async () => {
    await openOptions();
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "jev-strict" } });
    fireEvent.change(field("Context tokens"), { target: { value: "20000" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset to profile" }));
    expect(field("Scorer").value).toBe("rerank");
    expect(field("Context tokens").value).toBe("");
    expect(screen.queryByText("overridden")).toBeNull();
    expect(screen.getAllByRole("button", { name: /^Advanced/ })[1].textContent).toBe(
      "Advanced· low-vram values",
    );
  });

  it("an edit back to the profile's value no longer counts", async () => {
    await openOptions();
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "jev-strict" } });
    fireEvent.change(field("Scorer"), { target: { value: "rerank" } });
    expect(screen.queryByText("overridden")).toBeNull();
    expect(header()).not.toContain("custom (");
  });

  it("ends the segments with a selected custom while the profile has edits", async () => {
    await openOptions();
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "jev-strict" } });
    fireEvent.change(field("Write thinking"), { target: { value: "high" } });
    fireEvent.change(field("Context tokens"), { target: { value: "60000" } });
    expect(profileGroup().textContent).toBe("low-vramworkstationnixoscustom");
    expect((within(profileGroup()).getByLabelText("custom") as HTMLInputElement).checked).toBe(
      true,
    );
    expect((within(profileGroup()).getByLabelText("low-vram") as HTMLInputElement).checked).toBe(
      false,
    );
    expect(screen.getByText(/^based on/).textContent).toBe("based on low-vram · 3 edits");
  });

  it("offers Undo for the edits a profile switch drops", async () => {
    await openOptions();
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "jev-strict" } });
    fireEvent.change(field("Write thinking"), { target: { value: "high" } });
    fireEvent.change(field("Context tokens"), { target: { value: "60000" } });
    pickProfile("workstation");
    expect(screen.getByRole("status").textContent).toContain("Dropped 3 edits to low-vram");
    expect((within(profileGroup()).getByLabelText("workstation") as HTMLInputElement).checked).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect((within(profileGroup()).getByLabelText("custom") as HTMLInputElement).checked).toBe(
      true,
    );
    expect(header()).toContain("custom (low-vram)");
    expect(field("Scorer").value).toBe("jev-strict");
  });

  it("uses a select for more than six profiles", async () => {
    const api = fakeApi();
    for (const n of [1, 2, 3, 4])
      api.data.profiles.push({ ...api.data.profiles[1], name: `extra-${n}`, active: false });
    await openOptions(api);
    expect(screen.queryByRole("radiogroup", { name: "Profile" })).toBeNull();
    const select = screen.getByLabelText("Profile") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toHaveLength(7);
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "jev-strict" } });
    expect(select.value).toBe("__custom");
    expect(select.selectedOptions[0].textContent).toBe("custom (low-vram)");
  });

  it("drops the edits when the profile changes", async () => {
    await openOptions();
    profileAdvanced();
    fireEvent.change(field("Scorer"), { target: { value: "bm25" } });
    pickProfile("workstation");
    expect(field("Scorer").value).toBe("jev-strict");
    expect(screen.queryByText("overridden")).toBeNull();
  });

  it("sends auto for an emptied budget", async () => {
    const api = await openOptions();
    fireEvent.click(screen.getByLabelText("Deep"));
    profileAdvanced();
    fireEvent.change(field("Gap context tokens"), { target: { value: "" } });
    expect(screen.getByText("Auto · 30,000")).toBeTruthy();
    expect((await start(api)).llm).toEqual({ gap_context_tokens: "auto" });
  });

  it("locks the gap fields at one round", async () => {
    await openOptions();
    fireEvent.click(screen.getByLabelText("Quick"));
    profileAdvanced();
    expect(field("Gap thinking").disabled).toBe(true);
    expect(field("Gap context tokens").disabled).toBe(true);
    expect(screen.getAllByText("Used between rounds; needs 2+ rounds.")).toHaveLength(2);
  });

  it("offers the llm entry's models", async () => {
    const api = await openOptions(fakeApi({ models: ["a", "b"] }));
    profileAdvanced();
    await act(async () => {});
    expect(callsTo(api, "listModels")[0]).toEqual(["agents"]);
    const listed = [...document.querySelectorAll("#pa-model-list option")].map((o) =>
      o.getAttribute("value"),
    );
    expect(listed).toEqual(["a", "b"]);
  });

  it("No edits sent: neither use nor llm", async () => {
    const api = await openOptions();
    profileAdvanced();
    const request = await start(api);
    expect(request.use).toBeUndefined();
    expect(request.llm).toBeUndefined();
  });

  it("explains each field with the prototype's help", async () => {
    await openOptions();
    profileAdvanced();
    for (const label of ["Search", "Scorer", "LLM", "Model", "Context window", "Context tokens"])
      expect(screen.getAllByRole("button", { name: `Help: ${label}` }).length).toBeGreaterThan(0);
  });
});

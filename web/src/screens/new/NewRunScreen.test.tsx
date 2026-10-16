import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { RunCreate } from "../../api/types";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

async function open(api = fakeApi()) {
  renderApp({ hash: "#/new", api });
  const question = await screen.findByLabelText("Question");
  await screen.findByText("Options");
  return { api, question: question as HTMLTextAreaElement };
}

const ctrlEnter = (el: Element) =>
  act(async () => {
    fireEvent.keyDown(el, { key: "Enter", ctrlKey: true });
  });

describe("NewRunScreen", () => {
  it("shows the form with the question focused and Run disabled while blank", async () => {
    const { api, question } = await open();
    expect(screen.getByRole("heading", { name: "New research run" })).toBeTruthy();
    expect(screen.getByText(/wosarcher searches the web and your files/)).toBeTruthy();
    expect(document.activeElement).toBe(question);
    const run = screen.getByRole("button", { name: "Run research" }) as HTMLButtonElement;
    fireEvent.change(question, { target: { value: "   " } });
    expect(run.disabled).toBe(true);
    await ctrlEnter(question);
    expect(callsTo(api, "createRun")).toHaveLength(0);
  });

  it("starts with Ctrl+Enter and follows the new run on Live run", async () => {
    const { api, question } = await open();
    fireEvent.change(question, { target: { value: " What is RAG? " } });
    await ctrlEnter(question);
    const [request, files] = callsTo(api, "createRun")[0] as [RunCreate, File[]];
    expect(request).toEqual({
      query: "What is RAG?",
      sources: "both",
      profile: "low-vram",
      depth: "standard",
      writing: { format: "report" },
      questions: { clarify: true, rounds: true },
    });
    expect(files).toEqual([]);
    expect(window.location.hash).toBe("#/live/r_new1");
    expect(await screen.findByText("r_new1")).toBeTruthy();
  });

  it("sends the context recipe as until select, only overridden writing, and attachments", async () => {
    const { api, question } = await open();
    fireEvent.change(question, { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    fireEvent.click(screen.getByLabelText("context"));
    const words = screen.getByLabelText("Length (words)");
    fireEvent.change(words, { target: { value: "600" } });
    fireEvent.blur(words);
    const notes = new File(["# n"], "notes.md");
    fireEvent.change(screen.getByTestId("attachments-input"), { target: { files: [notes] } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run research" }));
    });
    const [request, files] = callsTo(api, "createRun")[0] as [RunCreate, File[]];
    expect(request.until).toBe("select");
    expect(request.writing).toEqual({ words: 600 });
    expect(files).toEqual([notes]);
  });

  it("sends the answer recipe as writing.format with no until", async () => {
    const { api, question } = await open();
    fireEvent.change(question, { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    fireEvent.click(screen.getByLabelText("answer"));
    expect(screen.getByRole("button", { name: /Options/ }).textContent).toContain(
      "Standard · answer · both",
    );
    expect(screen.queryByText(/overridden/)).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run research" }));
    });
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.until).toBeUndefined();
    expect(request.writing).toEqual({ format: "answer" });
  });

  it("sends Follow-ups per round and the trimmed search language", async () => {
    const { api, question } = await open();
    fireEvent.change(question, { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    fireEvent.click(screen.getByLabelText("Deep"));
    fireEvent.click(screen.getAllByRole("button", { name: /^Advanced/ })[0]);
    fireEvent.change(screen.getByLabelText("Follow-ups per round"), { target: { value: "6" } });
    const language = screen.getByLabelText("Search language");
    fireEvent.change(language, { target: { value: "spanish" } });
    expect(screen.getByText("Use all, auto, or a code such as es or es-PE.")).toBeTruthy();
    const run = screen.getByRole("button", { name: "Run research" }) as HTMLButtonElement;
    expect(run.disabled).toBe(true);
    fireEvent.change(language, { target: { value: " es-PE " } });
    expect(run.disabled).toBe(false);
    await act(async () => {
      fireEvent.click(run);
    });
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.research?.queries_per_round).toBe(6);
    expect(request.search_language).toBe("es-PE");
  });

  it("preselects the Recipe from the default format", async () => {
    const api = fakeApi();
    api.data.settings.writing.format = "answer";
    await open(api);
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    expect((screen.getByLabelText("answer") as HTMLInputElement).checked).toBe(true);
  });

  it("keeps the draft across screens", async () => {
    const { question } = await open();
    fireEvent.change(question, { target: { value: "draft question" } });
    await act(async () => {
      window.location.hash = "#/history";
    });
    await act(async () => {
      window.location.hash = "#/new";
    });
    expect(((await screen.findByLabelText("Question")) as HTMLTextAreaElement).value).toBe(
      "draft question",
    );
  });

  it("keeps the inputs and shows the server's message when the start is rejected", async () => {
    const api = fakeApi();
    const detail =
      'profile "gpu-box" does not exist. Known profiles: low-vram, workstation, cloud.';
    api.createRun = async () => {
      throw new ApiError(422, "invalid_request", detail);
    };
    const { question } = await open(api);
    fireEvent.change(question, { target: { value: "too long" } });
    await ctrlEnter(question);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Couldn’t start the run");
    expect(alert.textContent).toContain(detail);
    expect(screen.queryByRole("button", { name: "Fix in Options" })).toBeNull();
    expect(question.value).toBe("too long");
    expect(window.location.hash).toBe("#/new");
  });

  it("offers Fix in Options for a rejected domain entry", async () => {
    const api = fakeApi();
    const detail =
      "domains.allow: Value error, 'gob.pe/tramites' is not a domain; use the domain only, without a scheme, path, or port";
    api.createRun = async () => {
      throw new ApiError(422, "invalid_request", detail, {
        "domains.allow": detail.slice("domains.allow: ".length),
      });
    };
    const { question } = await open(api);
    fireEvent.change(question, { target: { value: "q" } });
    await ctrlEnter(question);
    expect(screen.getByRole("alert").textContent).toContain(detail);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Fix in Options" }));
    });
    expect(document.activeElement).toBe(screen.getByLabelText("Allow domains"));
  });

  it("catches an invalid entry before sending", async () => {
    const { api, question } = await open();
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    const allow = screen.getByLabelText("Allow domains");
    fireEvent.change(allow, { target: { value: "gob.pe/tramites" } });
    fireEvent.blur(allow);
    fireEvent.change(question, { target: { value: "q" } });
    await ctrlEnter(question);
    expect(callsTo(api, "createRun")).toHaveLength(0);
    expect(
      screen.getByText("Not a domain: gob.pe/tramites. Use the domain only, without a path."),
    ).toBeTruthy();
    expect(allow.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("alert").textContent).toContain("Couldn’t start the run");
    expect(screen.getByRole("button", { name: "Fix in Options" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove gob.pe/tramites" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("follows the global Allow default", async () => {
    const api = fakeApi();
    api.data.settings.domains.allow = ["gob.pe"];
    await open(api);
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    expect(screen.getByRole("button", { name: "Remove gob.pe" })).toBeTruthy();
    expect(screen.queryByText("overridden")).toBeNull();
  });
});

describe("NewRunScreen profile values", () => {
  const profileAdvanced = () =>
    fireEvent.click(screen.getAllByRole("button", { name: /^Advanced/ })[1]);

  it("asks the profile's llm entry for models", async () => {
    const { api } = await open(fakeApi({ models: ["m1"] }));
    expect(callsTo(api, "listProviders").length).toBeGreaterThan(0);
    await act(async () => {});
    expect(callsTo(api, "listModels")[0]).toEqual(["agents"]);
  });

  it("keeps the edits across screens and clears them after the run starts", async () => {
    const { api } = await open();
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    profileAdvanced();
    fireEvent.change(screen.getByLabelText("Plan thinking"), { target: { value: "default" } });
    await act(async () => {
      window.location.hash = "#/history";
    });
    await act(async () => {
      window.location.hash = "#/new";
    });
    fireEvent.click(await screen.findByRole("button", { name: /Options/ }));
    expect(screen.getByRole("button", { name: /Options/ }).textContent).toContain(
      "custom (low-vram)",
    );
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "q" } });
    await ctrlEnter(screen.getByLabelText("Question") as HTMLTextAreaElement);
    const [request] = callsTo(api, "createRun")[0] as [RunCreate, File[]];
    expect(request.llm).toEqual({ reasoning: { plan: "default" } });
    expect(request.use).toBeUndefined();
    await act(async () => {
      window.location.hash = "#/new";
    });
    fireEvent.click(await screen.findByRole("button", { name: /Options/ }));
    expect(screen.getByRole("button", { name: /Options/ }).textContent).not.toContain("custom (");
  });
});

const RAG = "How should RAG pipelines chunk Markdown docs?";
const research = {
  sub_queries: 4,
  results_per_query: 8,
  max_pages: 50,
  passages_per_query: 9,
  rounds: 2,
  queries_per_round: 3,
};

function ragApi() {
  const api = fakeApi();
  const [base] = api.data.runs;
  api.data.runs.unshift({
    ...base,
    run_id: "r1",
    query: RAG,
    status: "done",
    created: "2026-10-04T10:00:00Z",
    depth: "custom",
    profile: "workstation",
    form: {
      query: RAG,
      sources: "both",
      profile: "workstation",
      depth: "custom",
      research,
      writing: { format: "report", words: 1500 },
    },
    attachments: [
      { name: "rag-chunking.md", size: 6120 },
      { name: "api-docs-sample.md", size: 900 },
    ],
  });
  return api;
}

const recentToggle = () => screen.getByRole("button", { name: /^Recent & pinned/ });
const fillRow = (name: string) => {
  if (recentToggle().getAttribute("aria-expanded") === "false") fireEvent.click(recentToggle());
  fireEvent.click(screen.getByRole("button", { name: `Fill the form from: ${name}` }));
};

describe("Recent & pinned", () => {
  it("is a collapsed disclosure with the row count on a narrow window", async () => {
    await open(ragApi());
    await screen.findByText("· 8");
    expect(recentToggle().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("group", { name: "Recent" })).toBeNull();
  });

  it("shows No runs yet when there is no run", async () => {
    await open(fakeApi({ runs: [] }));
    fireEvent.click(recentToggle());
    expect(screen.getByText("No runs yet")).toBeTruthy();
    expect(
      screen.getByText("Runs you start show up here. Pin the ones you repeat to keep them on top."),
    ).toBeTruthy();
  });

  it("fills the form from a run without starting it", async () => {
    const { api, question } = await open(ragApi());
    await screen.findByText("· 8");
    fillRow(RAG);
    expect(question.value).toBe(RAG);
    expect(callsTo(api, "createRun")).toHaveLength(0);
    expect(screen.getByText(`from: ${RAG}`)).toBeTruthy();
    expect(screen.getAllByText(/reused from/)).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    expect(screen.getByRole("button", { name: /Options/ }).textContent).toContain(
      "Custom · report · both · workstation · 1500 words",
    );
    expect((screen.getByLabelText("Max pages") as HTMLInputElement).value).toBe("50");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("lists a catalog run with null writing and fills without starting a run", async () => {
    const api = fakeApi();
    const catalog = {
      ...api.data.runs[0],
      run_id: "run-catalog",
      query: "Catalog of rust crates",
      kind: "catalog" as const,
      writing: null,
      nodes: 7,
    };
    api.data.runs = [catalog];
    const { question } = await open(api);
    fillRow("Catalog of rust crates");
    expect(question.value).toBe("Catalog of rust crates");
    expect(callsTo(api, "createRun")).toHaveLength(0);
  });

  it("offers Undo when the form had a question", async () => {
    await open(ragApi());
    await screen.findByText("· 8");
    const question = screen.getByLabelText("Question") as HTMLTextAreaElement;
    fireEvent.change(question, { target: { value: "my own question" } });
    fillRow(RAG);
    expect(screen.getByRole("status").textContent).toContain(
      "Filled from “How should RAG pipelines chu…”",
    );
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(question.value).toBe("my own question");
    expect(screen.queryByText(/reused from/)).toBeNull();
  });

  it("drops the from tag when the form is edited", async () => {
    await open(ragApi());
    await screen.findByText("· 8");
    fillRow(RAG);
    expect(screen.getByText(`from: ${RAG}`)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    fireEvent.click(screen.getByLabelText("web"));
    expect(screen.queryByText(`from: ${RAG}`)).toBeNull();
  });

  it("sends reused attachments by name and uploads only new files", async () => {
    const { api } = await open(ragApi());
    await screen.findByText("· 8");
    fillRow(RAG);
    fireEvent.click(screen.getByRole("button", { name: "Remove api-docs-sample.md" }));
    const extra = new File(["x"], "extra.md");
    fireEvent.change(screen.getByTestId("attachments-input"), { target: { files: [extra] } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run research" }));
    });
    const [request, files] = callsTo(api, "createRun")[0] as [RunCreate, File[]];
    expect(request.reuse_attachments).toEqual({ run_id: "r1", names: ["rag-chunking.md"] });
    expect(request.research).toEqual(research);
    expect(files).toEqual([extra]);
  });

  it("pins and renames a row, kept in browser storage", async () => {
    await open(ragApi());
    await screen.findByText("· 8");
    fireEvent.click(recentToggle());
    fireEvent.click(screen.getByRole("button", { name: `Actions for ${RAG.slice(0, 40)}…` }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Pin" }));
    fireEvent.click(screen.getByRole("button", { name: `Actions for ${RAG.slice(0, 40)}…` }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename" }));
    const name = screen.getByLabelText("Name");
    fireEvent.change(name, { target: { value: "Weekly LLM digest" } });
    fireEvent.keyDown(name, { key: "Enter" });
    const pinned = screen.getByRole("group", { name: "Pinned" });
    expect(pinned.textContent).toContain("Weekly LLM digest");
    expect(JSON.parse(localStorage.getItem("wosarcher-run-pins") ?? "[]")).toEqual(["r1"]);
    expect(JSON.parse(localStorage.getItem("wosarcher-run-names") ?? "{}")).toEqual({
      r1: "Weekly LLM digest",
    });
  });
});

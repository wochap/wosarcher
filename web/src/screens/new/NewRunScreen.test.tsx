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
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
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

describe("NewRunScreen model and thinking", () => {
  it("asks the selected profile's endpoint for models and keeps the values in the browser", async () => {
    localStorage.clear();
    const { api, question } = await open(fakeApi({ models: ["m1"] }));
    expect(callsTo(api, "listModels")[0]).toEqual(["low-vram"]);
    fireEvent.click(screen.getByRole("button", { name: /Options/ }));
    fireEvent.click(screen.getByRole("button", { name: /Advanced/ }));
    fireEvent.change(screen.getByLabelText("Plan thinking"), { target: { value: "default" } });
    fireEvent.change(question, { target: { value: "q" } });
    await ctrlEnter(question);
    const [request] = callsTo(api, "createRun")[0] as [RunCreate, File[]];
    expect(request.llm).toEqual({ reasoning: { plan: "default" } });
    expect(JSON.parse(localStorage.getItem("wosarcher.llm") ?? "{}").reasoning.plan).toBe(
      "default",
    );
    localStorage.clear();
  });
});

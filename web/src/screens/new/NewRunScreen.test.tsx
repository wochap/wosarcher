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
    api.createRun = async () => {
      throw new ApiError(422, "invalid_request", "query: too long");
    };
    const { question } = await open(api);
    fireEvent.change(question, { target: { value: "too long" } });
    await ctrlEnter(question);
    expect(screen.getByRole("alert").textContent).toBe("query: too long");
    expect(question.value).toBe("too long");
    expect(window.location.hash).toBe("#/new");
  });
});

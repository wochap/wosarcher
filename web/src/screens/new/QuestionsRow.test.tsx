import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DraftRequest, RunCreate } from "../../api/types";
import { HELP } from "../../components/help";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { renderApp } from "../../test/renderApp";

async function open(api = fakeApi()) {
  renderApp({ hash: "#/new", api });
  const question = (await screen.findByLabelText("Question")) as HTMLTextAreaElement;
  return { api, question };
}

async function openOptions(api = fakeApi()) {
  const opened = await open(api);
  fireEvent.change(opened.question, { target: { value: "What is RAG?" } });
  fireEvent.click(screen.getByRole("button", { name: /^Options/ }));
  // The settings (and with them the row's defaults) load after the form shows.
  await screen.findByRole("radiogroup", { name: "Questions" });
  return opened;
}

const group = () => screen.getByRole("radiogroup", { name: "Questions" });
const pick = (label: string) =>
  act(() => {
    fireEvent.click(within(group()).getByRole("radio", { name: label }));
  });
const run = async (name: string) =>
  act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });

describe("Questions row, research form", () => {
  it("is preselected from the settings and sends both pauses as asked", async () => {
    const { api } = await openOptions();
    expect((within(group()).getByRole("radio", { name: "Ask" }) as HTMLInputElement).checked).toBe(
      true,
    );
    expect((screen.getByLabelText("Timeout") as HTMLInputElement).value).toBe("60");
    expect(screen.queryByText("overridden", { selector: ".tag" })).toBeNull();
    await run("Run research");
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.questions).toEqual({ clarify: true, rounds: true });
  });

  it("sends false for both with Don't ask and hides the timeout", async () => {
    const { api } = await openOptions();
    pick("Don’t ask");
    expect(screen.queryByLabelText("Timeout")).toBeNull();
    await run("Run research");
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.questions).toEqual({ clarify: false, rounds: false });
  });

  it("marks a timeout override, sends it, and Reset brings the default back", async () => {
    const { api } = await openOptions();
    fireEvent.change(screen.getByLabelText("Timeout"), { target: { value: "120" } });
    const options = screen.getByRole("button", { name: /^Options/ }).parentElement as HTMLElement;
    expect(within(options).getAllByText("overridden").length).toBeGreaterThan(0);
    expect(within(options).getByText("default: ask · 60 s")).toBeTruthy();
    act(() => {
      fireEvent.click(within(options).getAllByRole("button", { name: "Reset" })[0]);
    });
    expect((screen.getByLabelText("Timeout") as HTMLInputElement).value).toBe("60");
    fireEvent.change(screen.getByLabelText("Timeout"), { target: { value: "120" } });
    await run("Run research");
    const [request] = callsTo(api, "createRun")[0] as [RunCreate];
    expect(request.questions).toEqual({ clarify: true, rounds: true, timeout: 120 });
  });

  it("starts from the settings when they turn questions off", async () => {
    const api = fakeApi();
    api.data.settings.questions = { clarify: false, rounds: false, timeout: 30, max_wait: 1800 };
    const { api: used } = await openOptions(api);
    expect(
      (within(group()).getByRole("radio", { name: "Don’t ask" }) as HTMLInputElement).checked,
    ).toBe(true);
    await run("Run research");
    const [request] = callsTo(used, "createRun")[0] as [RunCreate];
    expect(request.questions).toEqual({ clarify: false, rounds: false });
  });

  it("has the Questions help", async () => {
    await openOptions();
    fireEvent.mouseEnter(screen.getByRole("button", { name: "Help: Questions" }));
    expect(screen.getByRole("tooltip").textContent).toContain(HELP["q-ask"].body);
  });

  it("is kept with the draft when the form is left and reopened", async () => {
    await openOptions();
    pick("Don’t ask");
    act(() => {
      window.location.hash = "#/history";
    });
    await screen.findByRole("heading", { name: "Run history" });
    act(() => {
      window.location.hash = "#/new";
    });
    await screen.findByLabelText("Question");
    fireEvent.click(screen.getByRole("button", { name: /^Options/ }));
    expect(
      (within(group()).getByRole("radio", { name: "Don’t ask" }) as HTMLInputElement).checked,
    ).toBe(true);
  });
});

describe("Run group, catalog form", () => {
  async function openCatalog(api = fakeApi()) {
    const { question } = await open(api);
    expect(question).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "Catalog" }));
    const brief = screen.getByLabelText("Brief") as HTMLTextAreaElement;
    return { api, brief };
  }

  it("shows the Profile and Questions rows as soon as Catalog is picked", async () => {
    await openCatalog();
    const runGroup = screen.getByText("Run", { selector: "span" }).closest("div")?.parentElement;
    expect(runGroup).toBeTruthy();
    expect(
      within(runGroup as HTMLElement).getByRole("radiogroup", { name: "Profile" }),
    ).toBeTruthy();
    await screen.findByRole("radiogroup", { name: "Questions" });
    expect(screen.queryByText("Drafted from your brief · edit anything")).toBeNull();
  });

  it("drafts with the chosen profile", async () => {
    const { api, brief } = await openCatalog();
    fireEvent.click(screen.getByRole("radio", { name: "workstation" }));
    fireEvent.change(brief, { target: { value: "Every public body" } });
    await run("Draft structure");
    const [request] = callsTo(api, "draftStructure")[0] as [DraftRequest];
    expect(request.profile).toBe("workstation");
    // The Profile row is no longer part of the Structure panel.
    const structure = screen.getByText("Structure").closest("div")?.parentElement as HTMLElement;
    expect(within(structure).queryByRole("radiogroup", { name: "Profile" })).toBeNull();
  });

  it("sends questions as asked by default and as overridden", async () => {
    const { api, brief } = await openCatalog();
    fireEvent.change(brief, { target: { value: "Every public body" } });
    await run("Draft structure");
    await run("Run catalog");
    expect((callsTo(api, "createRun")[0][0] as RunCreate).questions).toEqual({
      clarify: true,
      rounds: true,
    });
  });

  it("sends Don't ask and the timeout override", async () => {
    const { api, brief } = await openCatalog();
    fireEvent.change(brief, { target: { value: "Every public body" } });
    await run("Draft structure");
    fireEvent.change(screen.getByLabelText("Timeout"), { target: { value: "120" } });
    await run("Run catalog");
    expect((callsTo(api, "createRun")[0][0] as RunCreate).questions).toEqual({
      clarify: true,
      rounds: true,
      timeout: 120,
    });
  });

  it("sends false for both with Don't ask", async () => {
    const { api, brief } = await openCatalog();
    fireEvent.change(brief, { target: { value: "Every public body" } });
    await run("Draft structure");
    pick("Don’t ask");
    await run("Run catalog");
    expect((callsTo(api, "createRun")[0][0] as RunCreate).questions).toEqual({
      clarify: false,
      rounds: false,
    });
  });
});

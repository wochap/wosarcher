import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { finished } from "../../test/fixtures/finished";
import { MD1, QUERY, RUN_ID, reportJson, summary } from "../../test/fixtures/sample";
import { versions } from "../../test/fixtures/versions";
import { renderApp } from "../../test/renderApp";
import { openScenario } from "../../test/scenario";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Files the page saves through a link click, by name. */
function captureDownloads() {
  const saved: { name: string; blob: Blob }[] = [];
  const blobs = new Map<string, Blob>();
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: (b: Blob) => {
      const url = `blob:${blobs.size}`;
      blobs.set(url, b);
      return url;
    },
    revokeObjectURL() {},
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push({ name: this.download, blob: blobs.get(this.getAttribute("href") ?? "") as Blob });
  });
  return saved;
}

const press = (name: string | RegExp) =>
  act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });

function clipboard() {
  const writes: string[] = [];
  vi.stubGlobal("navigator", {
    clipboard: { writeText: async (t: string) => void writes.push(t) },
  });
  return writes;
}

function withReport(continuations: number, truncated: boolean) {
  const report = { ...reportJson(MD1, "numeric"), continuations, truncated };
  const own = finished.data.artifacts?.[RUN_ID] ?? {};
  return {
    ...finished,
    data: {
      ...finished.data,
      artifacts: { [RUN_ID]: { ...own, "report.json": JSON.stringify(report) } },
    },
  };
}

describe("ReportScreen continuation notes", () => {
  it("shows the continued note with its help", async () => {
    await openScenario(withReport(1, false));
    expect(
      await screen.findByText(/^Continued 1× after reaching the output limit\.$/),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Continued" })).toBeTruthy();
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.queryByText("Output limit reached here")).toBeNull();
  });

  it("shows the cut note and end marker for a report still cut off", async () => {
    await openScenario(withReport(2, true));
    const note = await screen.findByRole("note");
    expect(note.textContent).toBe(
      "Still cut off after 2 continuations. The last section may be incomplete.",
    );
    const end = screen.getByText("Output limit reached here");
    const references = screen.getByRole("heading", { name: /^References/ });
    expect(end.compareDocumentPosition(references) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText(/^Continued/)).toBeNull();
  });

  it("shows the cut note without continuations", async () => {
    await openScenario(withReport(0, true));
    expect((await screen.findByRole("note")).textContent).toBe(
      "Cut off at the output limit. The last section may be incomplete.",
    );
    expect(screen.getByText("Output limit reached here")).toBeTruthy();
  });

  it("shows no note for a normal report", async () => {
    await openScenario(withReport(0, false));
    await screen.findByRole("heading", { name: /^References/ });
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.queryByText(/^Continued/)).toBeNull();
    expect(screen.queryByText("Output limit reached here")).toBeNull();
  });
});

describe("ReportScreen", () => {
  it("ends a multi-round run's meta line with its rounds", async () => {
    const deep = summary({ depth: "deep", rounds_planned: 3, rounds_ran: 2 });
    const others = finished.data.runs?.filter((r) => r.run_id !== RUN_ID) ?? [];
    await openScenario({ ...finished, data: { ...finished.data, runs: [deep, ...others] } });
    expect(await screen.findByText(/ · 14 passages · 2 of 3 rounds$/)).toBeTruthy();
  });

  it("clamps a long question title and toggles the whole of it", async () => {
    const query = `# Brief\n${"x".repeat(4022)}`;
    const others = finished.data.runs?.filter((r) => r.run_id !== RUN_ID) ?? [];
    const long = summary({ query });
    await openScenario({ ...finished, data: { ...finished.data, runs: [long, ...others] } });
    const title = await screen.findByRole("heading", { level: 1, name: /^# Brief/ });
    expect(title.id).toBe("rep-q");
    const toggle = screen.getByRole("button", { name: /Show full question/ });
    expect(toggle.textContent).toBe("Show full question· 4,030 characters");
    expect(toggle.getAttribute("aria-controls")).toBe("rep-q");
    fireEvent.click(toggle);
    expect(toggle.textContent).toBe("Show less· 4,030 characters");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(title.textContent).toBe(query);
  });

  it("shows a short question title whole, with no toggle", async () => {
    const query = "y".repeat(120);
    const others = finished.data.runs?.filter((r) => r.run_id !== RUN_ID) ?? [];
    await openScenario({
      ...finished,
      data: { ...finished.data, runs: [summary({ query }), ...others] },
    });
    const title = await screen.findByRole("heading", { level: 1, name: query });
    expect(title.id).toBe("");
    expect(screen.queryByRole("button", { name: /Show full question/ })).toBeNull();
  });

  it("shows the finished report with its sources and selected passages", async () => {
    await openScenario(finished);
    expect(await screen.findByRole("heading", { level: 1, name: QUERY })).toBeTruthy();
    expect(screen.getByText("Completed")).toBeTruthy();
    expect(screen.getByText(/· 2:30 · report · 21 sources · 14 passages$/)).toBeTruthy();
    expect(
      screen.getByText("Written with Analytical · 1200 words · English · [1] Numeric · APA"),
    ).toBeTruthy();
    const article = screen.getByRole("article");
    expect(within(article).getByRole("heading", { name: "Recommendations" })).toBeTruthy();
    expect(within(article).getAllByRole("button", { name: /^Citation 1,/ })).toHaveLength(2);
    expect(within(article).getByRole("heading", { name: /^References/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Help: Rewrite" })).toBeTruthy();
    const aside = screen.getByRole("complementary");
    expect(within(aside).getByText("21 · 3 failed")).toBeTruthy();
    const eagle = within(aside).getByText(
      "EAGLE: Speculative Sampling Requires Rethinking Feature Uncertainty",
    );
    expect(eagle.closest("li")?.textContent).toContain("1 kept");
    expect(eagle.closest("li")?.textContent).toContain("[4]");
    expect(within(aside).getByText("Selected passages")).toBeTruthy();
    expect(within(aside).getAllByText("0.94").length).toBe(1);
    expect(screen.queryByRole("navigation", { name: "Report versions" })).toBeNull();
  });

  it("names the reference style after References and in Written with", async () => {
    const run = summary({ writing: { ...summary().writing, reference_style: "MLA" } });
    await openScenario({ ...finished, data: { ...finished.data, runs: [run] } });
    await screen.findByRole("heading", { level: 1, name: QUERY });
    const heading = screen.getByRole("heading", { name: /^References/ });
    expect(within(heading).getByText("MLA")).toBeTruthy();
    expect(within(heading).getByRole("button", { name: "Help: Reference style" })).toBeTruthy();
    expect(screen.getByText(/^Written with .* · MLA$/)).toBeTruthy();
  });

  it("shows a finished answer with its options line, actions, and References", async () => {
    const run = summary({ writing: { ...summary().writing, format: "answer", words: 400 } });
    await openScenario({ ...finished, data: { ...finished.data, runs: [run] } });
    await screen.findByRole("heading", { level: 1, name: QUERY });
    expect(screen.getByText(/· answer ·/)).toBeTruthy();
    expect(screen.getByText(/^Answer, at most 400 words · Analytical · English · /)).toBeTruthy();
    expect(screen.queryByText(/^Written with/)).toBeNull();
    for (const name of [
      /^Rewrite$/,
      /Copy markdown/,
      /Download .md/,
      /Download .pdf/,
      /Download .docx/,
    ]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
    expect(screen.getByRole("heading", { name: /^References/ })).toBeTruthy();
  });

  it("shows the selected passages instead of a report for the context recipe", async () => {
    const api = fakeApi(finished.data);
    api.data.runs[0] = summary({ until: "select" });
    await openScenario(finished, { api });
    await screen.findByRole("heading", { level: 1, name: QUERY });
    expect(screen.getByText(/· context ·/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Rewrite/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Copy markdown/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Download/ })).toBeNull();
    const article = screen.getByRole("article");
    expect(within(article).queryByRole("heading", { name: "Summary" })).toBeNull();
    expect(within(article).getByText(/Throughput gains track draft latency/)).toBeTruthy();
  });
});

describe("ReportScreen states", () => {
  it("shows Run not found for a deleted run", async () => {
    renderApp({ hash: "#/runs/r_deleted" });
    expect(await screen.findByRole("heading", { name: "Run not found" })).toBeTruthy();
    expect(screen.getByText(/Run r_deleted does not exist on this server/)).toBeTruthy();
  });

  it("announces the lineage's next version when rewriting an older one", async () => {
    await openScenario({ ...versions, runId: RUN_ID });
    await screen.findByRole("heading", { level: 1, name: QUERY });
    await press("Rewrite");
    expect(screen.getByRole("dialog").textContent).toContain(`Creates v3 linked to ${RUN_ID}`);
  });
});

describe("Export", () => {
  it("downloads <id>.md starting with the query", async () => {
    const saved = captureDownloads();
    await openScenario(finished);
    await screen.findByRole("heading", { level: 1, name: QUERY });
    await press(/Download .md/);
    expect(saved[0].name).toBe(`${RUN_ID}.md`);
    const text = await saved[0].blob.text();
    expect(text.startsWith(`# ${QUERY}\n\n## Summary`)).toBe(true);
    expect(screen.getByRole("status").textContent).toBe(`Downloaded ${RUN_ID}.md`);
  });

  it("shows the desktop downloads in order between Copy markdown and Copy JSON", async () => {
    await openScenario(finished);
    await screen.findByRole("heading", { level: 1, name: QUERY });
    const labels = screen.getAllByRole("button").map((b) => b.textContent);
    const start = labels.indexOf("Copy markdown");
    expect(labels.slice(start, start + 5)).toEqual([
      "Copy markdown",
      "Download .md",
      "Download .pdf",
      "Download .docx",
      "Copy JSON (context)",
    ]);
  });

  it("exports a PDF on desktop with the busy state, then saves it", async () => {
    const saved = captureDownloads();
    const api = fakeApi(finished.data);
    let finish: (blob: Blob) => void = () => {};
    api.exportRun = (id, format) => {
      api.calls.push({ method: "exportRun", args: [id, format] });
      return new Promise((resolve) => {
        finish = resolve;
      });
    };
    await openScenario(finished, { api });
    await screen.findByRole("heading", { level: 1, name: QUERY });
    await press(/Download .pdf/);
    const busy = screen.getByRole("button", { name: "Exporting…" });
    expect(busy.hasAttribute("disabled")).toBe(true);
    expect(busy.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByRole("button", { name: /Download .docx/ }).hasAttribute("disabled")).toBe(
      false,
    );
    await act(async () => finish(new Blob(["%PDF"])));
    expect(callsTo(api, "exportRun")).toEqual([[RUN_ID, "pdf"]]);
    expect(saved.map((s) => s.name)).toEqual([`${RUN_ID}.pdf`]);
    expect(screen.getByRole("status").textContent).toBe(`Downloaded ${RUN_ID}.pdf`);
    expect(screen.getByRole("button", { name: /Download .pdf/ }).hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("shows the server's detail in an error toast when export is unavailable", async () => {
    const saved = captureDownloads();
    const api = fakeApi(finished.data);
    const detail = "PDF export needs typst on the server";
    api.data.exports.pdf = new ApiError(503, "export_unavailable", detail);
    await openScenario(finished, { api });
    await screen.findByRole("heading", { level: 1, name: QUERY });
    await press(/Download .pdf/);
    expect(saved).toEqual([]);
    const toast = screen.getByRole("status");
    expect(toast.textContent).toBe(detail);
    expect(toast.querySelector("svg")?.getAttribute("class")).toMatch(/danger/);
  });

  it("offers a Download format menu on a phone", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("max-width"),
      addEventListener() {},
      removeEventListener() {},
    }));
    const saved = captureDownloads();
    await openScenario(finished);
    await screen.findByRole("heading", { level: 1, name: QUERY });
    expect(screen.queryByRole("button", { name: /Download .pdf/ })).toBeNull();
    const button = screen.getByRole("button", { name: "Download" });
    expect(button.getAttribute("aria-haspopup")).toBe("menu");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    await press("Download");
    const menu = screen.getByRole("menu", { name: "Download format" });
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((i) => i.textContent),
    ).toEqual([".mdMarkdown", ".pdfPDF", ".docxWord"]);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    await press("Download");
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
    await press("Download");
    await act(async () => {
      fireEvent.click(screen.getByRole("menuitem", { name: /\.docx/ }));
    });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(saved.map((s) => s.name)).toEqual([`${RUN_ID}.docx`]);
    expect(screen.getByRole("status").textContent).toBe(`Downloaded ${RUN_ID}.docx`);
  });

  it("copies the markdown and the context JSON", async () => {
    const writes = clipboard();
    const { api } = await openScenario(finished);
    await screen.findByRole("heading", { level: 1, name: QUERY });
    await press(/Copy markdown/);
    expect(writes[0]).toBe(api.data.artifacts[RUN_ID]["report.md"]);
    expect(screen.getByRole("status").textContent).toBe("Markdown copied");
    await press(/Copy JSON/);
    const json = JSON.parse(writes[1]);
    expect(Object.keys(json)).toEqual(["run", "parent", "query", "options", "passages"]);
    expect(json.options).toMatchObject({ recipe: "report", sources: "both", profile: "low-vram" });
    expect(json.options.writing.words).toBe(1200);
    expect(json.passages[0]).toEqual({
      cite: 1,
      score: 0.94,
      source: "https://arxiv.org/abs/2402.01528",
      heading_path: ["4 Results", "4.2 Draft size vs. latency"],
      text: expect.stringContaining("Throughput gains"),
    });
    expect(screen.getByRole("status").textContent).toBe("Context JSON copied");
    expect(callsTo(api, "getArtifact").map((c) => c[1])).toContain("report.md");
  });
});

describe("ReportScreen depth tag", () => {
  it("shows the run's depth after the status", async () => {
    await openScenario({
      ...finished,
      data: { ...finished.data, runs: [summary({ depth: "deep" })] },
    });
    const status = await screen.findByText("Completed");
    expect(status.closest("span")?.nextElementSibling?.textContent).toBe("Deep");
  });
});

describe("ReportScreen thinking tags", () => {
  it("shows writer thinking after the depth tag", async () => {
    const reasoning = { plan: "none", gap: "none", write: "high" } as const;
    await openScenario({
      ...finished,
      data: { ...finished.data, runs: [summary({ depth: "deep", reasoning })] },
    });
    const status = await screen.findByText("Completed");
    const depth = status.closest("span")?.nextElementSibling;
    expect(depth?.textContent).toBe("Deep");
    expect(depth?.nextElementSibling?.textContent).toBe("Write thinking high");
  });

  it("shows no thinking tag when every step is none", async () => {
    await openScenario(finished);
    await screen.findByText("Completed");
    expect(screen.queryByText(/thinking (low|medium|high|default)/)).toBeNull();
  });
});

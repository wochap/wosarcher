import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { finished } from "../../test/fixtures/finished";
import { MD1, QUERY, RUN_ID, reportJson, summary } from "../../test/fixtures/sample";
import { versions } from "../../test/fixtures/versions";
import { renderApp } from "../../test/renderApp";
import { openScenario } from "../../test/scenario";

afterEach(() => vi.unstubAllGlobals());

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
    const saved: { name: string; blob: Blob }[] = [];
    const blobs: Blob[] = [];
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: (b: Blob) => {
        blobs.push(b);
        return "blob:x";
      },
      revokeObjectURL() {},
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push({ name: this.download, blob: blobs[0] });
    });
    await openScenario(finished);
    await screen.findByRole("heading", { level: 1, name: QUERY });
    await press(/Download .md/);
    expect(saved[0].name).toBe(`${RUN_ID}.md`);
    const text = await saved[0].blob.text();
    expect(text.startsWith(`# ${QUERY}\n\n## Summary`)).toBe(true);
    expect(screen.getByRole("status").textContent).toBe(`Downloaded ${RUN_ID}.md`);
    click.mockRestore();
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

import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEvent, RunSummary } from "../../api/types";
import { ev } from "../../test/events";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { CATALOG_BRIEF, catalog, records, structure } from "../../test/fixtures/catalog";
import { runs } from "../../test/fixtures/data";
import { renderApp } from "../../test/renderApp";
import { play } from "../../test/scenario";

const base = runs.find((r) => r.status === "done") as RunSummary;
const catRun = (status: RunSummary["status"]): RunSummary => ({
  ...base,
  run_id: "r_cat",
  query: CATALOG_BRIEF,
  kind: "catalog",
  nodes: 6,
  model: "research-smart",
  use: { llm: "omniroute" },
  status,
  parent_run_id: null,
  fork_from: null,
  version: 1,
});

function api(status: RunSummary["status"] = "done") {
  return fakeApi({
    runs: [catRun(status), ...runs],
    artifacts: {
      r_cat: {
        "catalog.json": JSON.stringify(catalog),
        "structure.json": JSON.stringify(structure),
      },
    },
  });
}

describe("CatalogScreen", () => {
  it("shows the result at #/runs/<id> of a catalog run, with a missing-field filter", async () => {
    renderApp({ hash: "#/runs/r_cat", api: api() });
    expect(await screen.findByRole("heading", { name: CATALOG_BRIEF })).toBeTruthy();
    expect(screen.getByText(/· catalog · 6 nodes · \d+ sources/)).toBeTruthy();
    expect(screen.getByText("6 records")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show records missing website" }));
    expect(screen.getByText("3 of 6")).toBeTruthy();
  });

  it("opens the drawer from the graph and closes it with Escape", async () => {
    renderApp({ hash: "#/catalog/r_cat", api: api() });
    await screen.findByRole("heading", { name: CATALOG_BRIEF });
    fireEvent.click(screen.getByRole("radio", { name: "Graph" }));
    fireEvent.click(screen.getByRole("button", { name: /^Superintendencia Nacional de Aduanas/ }));
    const drawer = screen.getByRole("dialog", { name: /Superintendencia/ });
    expect(within(drawer).getByText("Pages used")).toBeTruthy();
    expect(within(drawer).getAllByRole("link").length).toBeGreaterThan(0);
    fireEvent.keyDown(drawer, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: /Superintendencia/ })).toBeNull();
  });

  it("forks from expand with the raised limits", async () => {
    const fake = api();
    renderApp({ hash: "#/catalog/r_cat", api: fake });
    await screen.findByRole("heading", { name: CATALOG_BRIEF });
    fireEvent.click(screen.getByRole("button", { name: "Expand more" }));
    fireEvent.change(screen.getByLabelText("Max depth"), { target: { value: "4" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Expand from the frontier" }));
    });
    expect(callsTo(fake, "forkRun")[0]).toEqual([
      "r_cat",
      { from: "expand", limits: { max_depth: 4, max_nodes: 200, pages_per_node: 2 } },
    ]);
    expect(window.location.hash).toMatch(/^#\/live\//);
  });

  async function openReextract() {
    const fake = api();
    renderApp({ hash: "#/catalog/r_cat", api: fake });
    await screen.findByRole("heading", { name: CATALOG_BRIEF });
    fireEvent.click(screen.getByRole("button", { name: "Re-extract" }));
    await act(async () => {});
    return { fake, dialog: screen.getByRole("dialog", { name: "Re-extract" }) };
  }

  it("re-extracts with a model and Extract thinking", async () => {
    const { fake, dialog } = await openReextract();
    expect(dialog.textContent).toContain("Creates v2 linked to r_cat");
    fireEvent.change(within(dialog).getByLabelText("Model"), {
      target: { value: "deepseek-v4-flash" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^Extract thinking/), {
      target: { value: "medium" },
    });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Re-extract" }));
    });
    expect(callsTo(fake, "forkRun")[0]).toEqual([
      "r_cat",
      {
        from: "extract",
        llm: { model: "deepseek-v4-flash", reasoning: { extract: "medium" } },
      },
    ]);
  });

  it("re-extracts on another entry", async () => {
    const { fake, dialog } = await openReextract();
    fireEvent.change(within(dialog).getByLabelText("LLM entry"), { target: { value: "agents" } });
    expect((within(dialog).getByLabelText("Model") as HTMLInputElement).value).toBe("qwen3-14b");
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Re-extract" }));
    });
    expect(callsTo(fake, "forkRun")[0]).toEqual([
      "r_cat",
      { from: "extract", use: { llm: "agents" } },
    ]);
  });

  it("shows no Context tokens row when re-extracting", async () => {
    const { dialog } = await openReextract();
    for (const label of ["LLM entry", "Model", "Context window", "Max output"]) {
      expect(within(dialog).getByLabelText(label)).toBeTruthy();
    }
    expect(within(dialog).getByLabelText(/^Extract thinking/)).toBeTruthy();
    expect(within(dialog).queryByLabelText("Context tokens")).toBeNull();
  });

  it("shows a live catalog run's frontier, records, and footer", async () => {
    const fake = api("running");
    const events: RunEvent[] = [
      ev(
        1,
        "run.started",
        {
          query: CATALOG_BRIEF,
          kind: "catalog",
          profile: "p",
          parent_run_id: null,
          version: 1,
          until: null,
        },
        null,
        "r_cat",
      ),
      ev(
        2,
        "structure.ready",
        {
          fields: structure.fields.map((f) => ({ name: f.name, type: f.type })),
          seeds: 6,
          relation: "r",
          limits: { max_depth: 3, max_nodes: 200, pages_per_node: 2 },
          derived: false,
        },
        "draft",
        "r_cat",
      ),
      ev(
        3,
        "node.found",
        {
          node_id: "inei",
          name: "INEI",
          type: "public_body",
          parent_id: null,
          depth: 0,
          url: null,
          wave: 1,
          found_by: "seed",
        },
        "draft",
        "r_cat",
      ),
      ev(4, "stage.started", { device: null, provider: "built-in", round: 3 }, "expand", "r_cat"),
      ev(
        5,
        "node.extracted",
        {
          node_id: "inei",
          record: { name: "INEI", website: null },
          sources: {},
          flags: ["head_name from a source dated 2025-10-02"],
          children: 0,
        },
        "extract",
        "r_cat",
      ),
    ];
    renderApp({ hash: "#/live/r_cat", api: fake });
    await play("r_cat", events);
    expect(await screen.findByRole("treeitem", { name: /INEI.*extracted/ })).toBeTruthy();
    const records = screen.getByRole("region", { name: "Records" });
    expect(within(records).getByText("head_name from a source dated 2025-10-02")).toBeTruthy();
    expect(within(records).getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getAllByText("wave 3").length).toBeGreaterThan(1);
    expect(screen.getByText("1 extracted")).toBeTruthy();
  });

  describe("live samples", () => {
    const liveEvents = (extra: RunEvent[]): RunEvent[] => [
      ev(
        1,
        "run.started",
        {
          query: CATALOG_BRIEF,
          kind: "catalog",
          profile: "p",
          parent_run_id: null,
          version: 1,
          until: null,
        },
        null,
        "r_cat",
      ),
      ev(
        2,
        "structure.ready",
        {
          fields: structure.fields.map((f) => ({
            name: f.name,
            type: f.type,
            description: f.description ?? "",
          })),
          seeds: 6,
          relation: "r",
          limits: { max_depth: 3, max_nodes: 200, pages_per_node: 2 },
          derived: false,
        },
        "draft",
        "r_cat",
      ),
      ...["mef", "pcm", "inei"].map((id, i) =>
        ev(
          3 + i,
          "node.found",
          {
            node_id: id,
            name: id.toUpperCase(),
            type: "public_body",
            parent_id: null,
            depth: 0,
            url: null,
            wave: 1,
            found_by: "seed",
          },
          "draft",
          "r_cat",
        ),
      ),
      ...extra,
    ];
    const extractedEvent = (
      seq: number,
      id: string,
      record: Record<string, unknown>,
      sources = {},
    ) =>
      ev(
        seq,
        "node.extracted",
        { node_id: id, record, sources, flags: [], children: 0 },
        "extract",
        "r_cat",
      );

    it("shows the first sample with its source, and keeps it", async () => {
      renderApp({ hash: "#/live/r_cat", api: api("running") });
      const fill = () => screen.getByRole("region", { name: "Fill per field" });
      await play("r_cat", liveEvents([extractedEvent(6, "mef", { name: "MEF", website: null })]));
      expect(await within(fill()).findAllByText("— nothing found yet")).toBeTruthy();
      await play("r_cat", [
        extractedEvent(
          7,
          "pcm",
          { name: "PCM", website: "https://www.gob.pe/mef" },
          {
            website: "https://www.gob.pe/mef",
          },
        ),
      ]);
      expect(within(fill()).getByText("https://www.gob.pe/mef")).toBeTruthy();
      const link = within(fill()).getByRole("link", { name: "Open the page website came from" });
      expect(link.getAttribute("href")).toBe("https://www.gob.pe/mef");
      await play("r_cat", [
        extractedEvent(8, "inei", { name: "INEI", website: "https://other.pe" }),
      ]);
      expect(within(fill()).getByText("https://www.gob.pe/mef")).toBeTruthy();
      expect(within(fill()).queryByText("https://other.pe")).toBeNull();
    });

    it("shows the description in a tip titled with the field", async () => {
      renderApp({ hash: "#/live/r_cat", api: api("running") });
      await play("r_cat", liveEvents([]));
      const fill = await screen.findByRole("region", { name: "Fill per field" });
      fireEvent.mouseEnter(within(fill).getByRole("button", { name: "Description of head_name" }));
      const tip = await screen.findByRole("tooltip");
      expect(tip.textContent).toContain("head_name");
      expect(tip.textContent).toContain("Name of the current holder");
    });
  });

  it("lists every field with its fill and sample, and opens the sample's record", async () => {
    renderApp({ hash: "#/catalog/r_cat", api: api() });
    await screen.findByRole("heading", { name: CATALOG_BRIEF });
    const aside = screen.getByRole("complementary", { name: "Summary" });
    const open = within(aside).getByRole("button", {
      name: "Open the record behind the head_name sample",
    });
    expect(aside.textContent).toContain("1/6");
    expect(aside.textContent).toContain("R. Salazar");
    fireEvent.click(open);
    expect(screen.getByRole("dialog", { name: /Ministerio de Economía/ })).toBeTruthy();
  });

  it("shows — and does nothing for a field no record has", async () => {
    const empty = { ...catalog, records: records.map((r) => ({ ...r, website: null })) };
    const fake = fakeApi({
      runs: [catRun("done"), ...runs],
      artifacts: {
        r_cat: {
          "catalog.json": JSON.stringify(empty),
          "structure.json": JSON.stringify(structure),
        },
      },
    });
    renderApp({ hash: "#/catalog/r_cat", api: fake });
    await screen.findByRole("heading", { name: CATALOG_BRIEF });
    const aside = screen.getByRole("complementary", { name: "Summary" });
    const button = within(aside).getByRole("button", {
      name: "Open the record behind the website sample",
    }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.closest("li")?.textContent).toContain("0/6");
    expect(button.closest("li")?.textContent).toContain("—");
  });

  it("re-extracts with a changed description", async () => {
    const { fake, dialog } = await openReextract();
    const input = within(dialog).getByLabelText("Description of head_name");
    fireEvent.change(input, { target: { value: "Current minister's full name" } });
    expect(within(dialog).getByText("Fields · 1 changed")).toBeTruthy();
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Re-extract" }));
    });
    expect(callsTo(fake, "forkRun")[0]).toEqual([
      "r_cat",
      { from: "extract", fields: { head_name: "Current minister's full name" } },
    ]);
    expect(await screen.findByText(/pages reused · 1 description changed$/)).toBeTruthy();
  });

  it("re-extracts without changes and sends no fields", async () => {
    const { fake, dialog } = await openReextract();
    expect(dialog.textContent).toContain(
      "Changed descriptions are sent to the new run; pages are not fetched again.",
    );
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Re-extract" }));
    });
    expect(callsTo(fake, "forkRun")[0]).toEqual(["r_cat", { from: "extract" }]);
    expect(await screen.findByText(/Re-extract started as .* · pages reused$/)).toBeTruthy();
  });

  it("streams a catalog report in a ninth Write phase with a Coverage toggle", async () => {
    const fake = fakeApi({
      runs: [{ ...catRun("running"), output: "both" }, ...runs],
      artifacts: { r_cat: {} },
    });
    const done = { waves: 1, nodes: 1, records: 1, flagged: 0, reason: "frontier empty" };
    const events: RunEvent[] = [
      ev(
        1,
        "run.started",
        {
          query: CATALOG_BRIEF,
          kind: "catalog",
          profile: "p",
          parent_run_id: null,
          version: 1,
          until: null,
        },
        null,
        "r_cat",
      ),
      ev(2, "catalog.done", { ...done, note: "" } as never, "assemble", "r_cat"),
      ev(3, "stage.started", { device: null, provider: "llm", round: 1 }, "write", "r_cat"),
      ev(4, "report.delta", { text: "SUNAT reports to the MEF [1]." }, "write", "r_cat"),
    ];
    renderApp({ hash: "#/live/r_cat", api: fake });
    await play("r_cat", events);
    const phases = within(await screen.findByRole("list", { name: "Phases" })).getAllByRole(
      "listitem",
    );
    expect(phases).toHaveLength(9);
    expect(phases[8].textContent).toContain("Write");
    expect(phases[8].dataset.state).toBe("running");
    const report = screen.getByRole("region", { name: "Report" });
    expect(report.textContent).toContain("SUNAT reports to the MEF");
    fireEvent.click(within(report).getByRole("button", { name: "Coverage" }));
    expect(screen.getByRole("region", { name: "Coverage" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Report" })).toBeNull();
  });

  it("keeps eight phases for a table-only catalog", async () => {
    renderApp({ hash: "#/live/r_cat", api: api("running") });
    await play("r_cat", [
      ev(
        1,
        "run.started",
        {
          query: CATALOG_BRIEF,
          kind: "catalog",
          profile: "p",
          parent_run_id: null,
          version: 1,
          until: null,
        },
        null,
        "r_cat",
      ),
    ]);
    const phases = within(await screen.findByRole("list", { name: "Phases" })).getAllByRole(
      "listitem",
    );
    expect(phases).toHaveLength(8);
  });

  const context = {
    query: CATALOG_BRIEF,
    passages: [
      {
        n: 1,
        chunk_id: "record:sunat",
        source_id: "s1",
        query_id: "q0",
        text: "SUNAT\npublic_body\nacronym: SUNAT",
        heading_path: ["public_body"],
        scorer: "catalog",
        record_id: "sunat",
      },
    ],
    sources: [{ source_id: "s1", kind: "web", uri: "https://www.gob.pe/sunat", title: "SUNAT" }],
    budget_tokens: 1000,
    used_tokens: 10,
  };
  const report = {
    body: "SUNAT collects taxes [1].",
    markdown: "SUNAT collects taxes [1].",
    cited: [1],
    references: [{ source_id: "s1", entry: "SUNAT. gob.pe", passages: [1] }],
    records: true,
  };
  const withReport = (output: "both" | "report") =>
    fakeApi({
      runs: [{ ...catRun("done"), output }, ...runs],
      artifacts: {
        r_cat: {
          "catalog.json": JSON.stringify(catalog),
          "structure.json": JSON.stringify(structure),
          "report.json": JSON.stringify(report),
          "report.md": report.markdown,
          "context.json": JSON.stringify(context),
        },
      },
    });

  it("shows the Report view of a catalog with output both, and a citation opens the record", async () => {
    renderApp({ hash: "#/catalog/r_cat", api: withReport("both") });
    await screen.findByRole("heading", { name: CATALOG_BRIEF });
    expect(screen.getByRole("button", { name: "Copy markdown" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download .md" })).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "Report" }));
    const article = await screen.findByRole("article", { name: "Report" });
    expect(await within(article).findByText(/SUNAT collects taxes/)).toBeTruthy();
    const chip = within(article).getByRole("button", { name: "Citation 1, open record" });
    fireEvent.mouseEnter(chip);
    expect(screen.getByRole("tooltip").textContent).toContain("Open record");
    await act(async () => {
      fireEvent.click(chip);
    });
    expect(window.location.hash).toBe("#/catalog/r_cat/records/sunat");
  });

  it("shows a report-only catalog on the Report screen with a Records action", async () => {
    const fake = withReport("report");
    renderApp({ hash: "#/runs/r_cat", api: fake });
    await play("r_cat", [
      ev(
        1,
        "run.started",
        {
          query: CATALOG_BRIEF,
          kind: "catalog",
          profile: "p",
          parent_run_id: null,
          version: 1,
          until: null,
        },
        null,
        "r_cat",
      ),
      ev(2, "stage.done", { count: 1, seconds: 1, skipped: false } as never, "write", "r_cat"),
      ev(3, "run.done", { until: null } as never, null, "r_cat"),
    ]);
    const records = await screen.findByRole("button", { name: "Records" });
    expect(screen.queryByRole("button", { name: "Rewrite" })).toBeNull();
    expect(await screen.findByText(/SUNAT collects taxes/)).toBeTruthy();
    await act(async () => {
      fireEvent.click(records);
    });
    expect(window.location.hash).toBe("#/catalog/r_cat/records");
    expect(await screen.findByText("6 records")).toBeTruthy();
  });
});

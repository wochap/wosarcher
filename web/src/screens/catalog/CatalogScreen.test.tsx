import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEvent, RunSummary } from "../../api/types";
import { ev } from "../../test/events";
import { callsTo, fakeApi } from "../../test/fakeApi";
import { CATALOG_BRIEF, catalog, structure } from "../../test/fixtures/catalog";
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
  status,
  parent_run_id: null,
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

  it("re-extracts with a model and Extract thinking", async () => {
    const fake = api();
    renderApp({ hash: "#/catalog/r_cat", api: fake });
    await screen.findByRole("heading", { name: CATALOG_BRIEF });
    fireEvent.click(screen.getByRole("button", { name: "Re-extract" }));
    const dialog = screen.getByRole("dialog", { name: "Re-extract" });
    fireEvent.change(within(dialog).getByLabelText("Model"), {
      target: { value: "qwen3-30b-a3b" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^Extract thinking/), {
      target: { value: "medium" },
    });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Re-extract" }));
    });
    expect(callsTo(fake, "forkRun")[0]).toEqual([
      "r_cat",
      { from: "extract", llm: { model: "qwen3-30b-a3b", reasoning: { extract: "medium" } } },
    ]);
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
});

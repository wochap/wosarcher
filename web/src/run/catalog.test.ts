import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import { ev, stageDone } from "../test/events";
import { structure } from "../test/fixtures/catalog";
import {
  catalogRequest,
  clampLimit,
  estimate,
  fieldName,
  fillPercents,
  frontierRows,
  liveRecords,
  nodeValues,
  phaseCards,
  structureRow,
} from "./catalog";
import { initialRunView, type RunView, runReducer } from "./reducer";

const fold = (events: RunEvent[]): RunView => events.reduce(runReducer, initialRunView("r1"));

const found = (seq: number, id: string, parent: string | null, depth: number, wave = 1) =>
  ev(
    seq,
    "node.found",
    {
      node_id: id,
      name: id.toUpperCase(),
      type: depth ? "public_body" : "power",
      parent_id: parent,
      depth,
      url: null,
      wave,
      found_by: depth ? "links" : "seed",
    },
    "draft",
  );

const extracted = (
  seq: number,
  id: string,
  record: Record<string, unknown>,
  flags: string[] = [],
) =>
  ev(
    seq,
    "node.extracted",
    { node_id: id, record, sources: { acronym: `https://${id}.gob.pe` }, flags, children: 2 },
    "extract",
  );

const started = (seq: number, stage: string, round: number) =>
  ev(seq, "stage.started", { device: null, provider: "built-in", round }, stage as never);

const base = [
  ev(1, "run.started", {
    query: "q",
    kind: "catalog",
    profile: "p",
    parent_run_id: null,
    version: 1,
    until: null,
  }),
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
  ),
  found(3, "pe", null, 0),
  found(4, "pcm", "pe", 1),
  found(5, "inei", "pcm", 2),
  found(6, "bcrp", null, 0),
];

describe("catalog form", () => {
  it("estimates nodes, pages, and extraction calls", () => {
    expect(estimate({ max_depth: 3, max_nodes: 200, pages_per_node: 2 })).toBe(
      "Up to 200 nodes · about 400 pages · 200 extraction calls",
    );
    expect(estimate({ max_depth: 3, max_nodes: 50, pages_per_node: 2 })).toBe(
      "Up to 50 nodes · about 100 pages · 50 extraction calls",
    );
    expect(estimate({ max_depth: 3, max_nodes: Number.NaN, pages_per_node: 2 })).toBe(
      "Up to 0 nodes · about 0 pages · 0 extraction calls",
    );
  });

  it("normalises field names and clamps limits", () => {
    expect(fieldName("head  name x")).toBe("head_name_x");
    expect(clampLimit("max_nodes", 9000)).toBe(5000);
    expect(clampLimit("max_depth", 0)).toBe(1);
  });

  it("builds the run request", () => {
    const request = catalogRequest({
      brief: "  Every body ",
      structure: {
        ...structure,
        fields: [{ name: "head name", type: "text" }, ...structure.fields],
      },
      profile: "low-vram",
      domains: { allow: ["gob.pe"] },
      searchLanguage: " es ",
      choice: { use: {}, edits: {} },
    });
    expect(request.query).toBe("Every body");
    expect(request.kind).toBe("catalog");
    expect(request.profile).toBe("low-vram");
    expect(request.domains).toEqual({ allow: ["gob.pe"] });
    expect(request.search_language).toBe("es");
    expect(request.structure?.fields[0].name).toBe("head_name");
    expect(request.structure?.limits).toEqual({ max_depth: 3, max_nodes: 200, pages_per_node: 2 });
    expect(request).not.toHaveProperty("writing");
    expect(request).not.toHaveProperty("depth");
  });

  it("maps a rejected structure path to its row", () => {
    expect(structureRow({ "structure.seeds": "bad type" })).toBe("c-seeds");
    expect(structureRow({ "structure.limits.max_nodes": "too big" })).toBe("c-limits");
    expect(structureRow({ "domains.allow": "x" })).toBeNull();
  });
});

describe("catalog reducer", () => {
  it("builds the frontier tree in discovery order and collapses", () => {
    const live = fold(base).catalog;
    if (!live) throw new Error("no catalog");
    const rows = frontierRows(live).map((r) => [r.node.id, r.level, r.hasChildren]);
    expect(rows).toEqual([
      ["pe", 0, true],
      ["pcm", 1, true],
      ["inei", 2, false],
      ["bcrp", 0, false],
    ]);
    expect(frontierRows(live, new Set(["pe"])).map((r) => r.node.id)).toEqual(["pe", "bcrp"]);
  });

  it("marks discovered nodes expanding when a wave expands, and counts the wave", () => {
    const view = fold([...base, stageDone(7, "draft"), started(8, "expand", 3)]);
    expect(view.catalog?.wave).toBe(3);
    expect(view.catalog?.nodes.pe.status).toBe("expanding");
    const cards = phaseCards(view.catalog ?? (null as never), Date.now());
    expect(cards.find((c) => c.id === "expand")?.loop).toBe("wave 3");
    expect(cards.find((c) => c.id === "expand")?.text).toBe("4 nodes expanding");
    expect(cards.find((c) => c.id === "draft")?.text).toBe("12 fields · 6 seeds");
  });

  it("lists records newest first with flags, and counts failures", () => {
    const view = fold([
      ...base,
      extracted(7, "pcm", { name: "PCM", acronym: "PCM" }),
      extracted(8, "inei", { name: "INEI", website: null }, [
        "head_name from a source dated 2025-10-02",
      ]),
      ev(9, "node.failed", { node_id: "bcrp", reason: "timeout" }, "extract"),
    ]);
    const live = view.catalog;
    if (!live) throw new Error("no catalog");
    expect(liveRecords(live).map((n) => n.id)).toEqual(["inei", "pcm"]);
    expect(live.nodes.inei.flags).toEqual(["head_name from a source dated 2025-10-02"]);
    expect(live.nodes.inei.status).toBe("extracted");
    expect(live.failed).toBe(1);
    expect(live.nodes.bcrp.status).toBe("failed");
    const values = nodeValues(live.nodes.inei, live.fields);
    expect(values.id).toBe("inei");
    expect(values.type).toBe("public_body");
    expect(values.parent_id).toBe("pcm");
    expect(values.website).toBeNull();
  });

  it("computes fill percentages, lowest first", () => {
    const fill = fillPercents(
      [
        { a: 1, b: null, c: 1 },
        { a: 1, b: null, c: null },
        { a: 1, b: 2, c: 1 },
        { a: 1, b: null, c: 1 },
      ],
      ["a", "b", "c"],
    );
    expect(fill).toEqual([
      { field: "b", pct: 25 },
      { field: "c", pct: 75 },
      { field: "a", pct: 100 },
    ]);
  });

  it("ends every phase on catalog.done", () => {
    const view = fold([
      ...base,
      started(7, "expand", 1),
      stageDone(8, "expand"),
      started(9, "extract", 1),
      ev(
        10,
        "catalog.done",
        {
          waves: 5,
          nodes: 120,
          records: 118,
          flagged: 12,
          reason: "frontier empty",
          note: "",
        },
        "assemble",
      ),
    ]);
    const cards = phaseCards(view.catalog ?? (null as never), Date.now());
    expect(cards.every((c) => c.state === "done")).toBe(true);
    expect(cards.find((c) => c.id === "fetch")?.loop).toBe("5 waves");
    expect(cards.find((c) => c.id === "assemble")?.text).toBe("118 records · 12 flagged");
  });

  it("leaves research runs without a catalog", () => {
    expect(
      fold([
        ev(1, "run.started", {
          query: "q",
          profile: "p",
          parent_run_id: null,
          version: 1,
          until: null,
        }),
      ]).catalog,
    ).toBeNull();
  });
});

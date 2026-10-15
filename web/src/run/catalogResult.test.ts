import { describe, expect, it } from "vitest";
import { records, structure } from "../test/fixtures/catalog";
import {
  byDepth,
  catalogCsv,
  columnsOf,
  filterRecords,
  graphLayout,
  NO_FILTERS,
  worstFilled,
} from "./catalogResult";

const fields = columnsOf(structure, records);

describe("catalog result", () => {
  it("builds CSV with one column per field plus flags, quoting where needed", () => {
    const csv = catalogCsv(records, fields).split("\n");
    expect(csv[0].split(",")).toHaveLength(13);
    expect(csv[0].endsWith(",flags")).toBe(true);
    expect(csv).toHaveLength(records.length + 1);
    expect(csv.find((l) => l.startsWith("sunat,"))).toContain('"Tax ""and"" customs, Peru"');
    expect(
      csv.find((l) => l.startsWith("mef,"))?.endsWith("head_name from a source dated 2025-10-02"),
    ).toBe(true);
  });

  it("filters by search, type, flagged, and missing field", () => {
    const ids = (f = NO_FILTERS) => filterRecords(records, fields, f).map((r) => r.id);
    expect(ids({ ...NO_FILTERS, q: "sunat" })).toEqual(["sunat"]);
    expect(ids({ ...NO_FILTERS, q: "economía" })).toEqual(["mef"]);
    expect(ids({ ...NO_FILTERS, types: ["ministry"] })).toEqual(["pcm", "mef"]);
    expect(ids({ ...NO_FILTERS, flagged: true })).toEqual(["mef", "inei"]);
    expect(ids({ ...NO_FILTERS, missing: "website" })).toEqual(["poder-ejecutivo", "mef", "inei"]);
    expect(ids()).toHaveLength(records.length);
  });

  it("counts depths and the least filled fields", () => {
    expect(byDepth(records, fields)).toEqual([
      [0, 2],
      [1, 2],
      [2, 2],
    ]);
    expect(worstFilled(records, fields).map((w) => w.field)).toEqual([
      "head_name",
      "description",
      "website",
    ]);
  });

  it("lays the graph out left to right with parents centred on their children", () => {
    const g = graphLayout(records, fields);
    const at = (id: string) => g.nodes.find((n) => n.id === id) ?? { x: -1, y: -1 };
    expect(at("poder-ejecutivo").x).toBe(24);
    expect(at("pcm").x).toBe(24 + 230);
    expect(at("sunat").x).toBe(24 + 460);
    // Leaves take one row each in order: inei, sunat, bcrp.
    expect(at("inei").y).toBe(20);
    expect(at("sunat").y).toBe(44);
    expect(at("bcrp").y).toBe(68);
    expect(at("poder-ejecutivo").y).toBe((20 + 44) / 2);
    expect(g.edges).toHaveLength(4);
    expect(g.height).toBe(20 * 2 + 2 * 24);
  });
});

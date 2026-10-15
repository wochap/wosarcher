// The Catalog result screen's data: columns, CSV, filters, depth, fill, and the graph layout,
// all from `catalog.json` (and `structure.json` when it is there).
import type { CatalogRecord, Structure, StructureField } from "../api/types";
import { nameField, shortField } from "./catalog";

type Field = Pick<StructureField, "name" | "type">;

const EXTRA = new Set(["sources", "flags"]);

/** The structure's fields; without a structure, the first record's keys as text fields. */
export function columnsOf(structure: Structure | null, records: CatalogRecord[]): Field[] {
  if (structure) return structure.fields.map((f) => ({ name: f.name, type: f.type }));
  const keys = Object.keys(records[0] ?? {}).filter((k) => !EXTRA.has(k));
  return keys.map((name) => ({
    name,
    type: name === "id" ? "slug" : name === "type" ? "enum" : name === "parent_id" ? "ref" : "text",
  }));
}

const fieldOf = (fields: Field[], type: Field["type"]) => fields.find((f) => f.type === type)?.name;

/** The record's ID: its slug field. */
export function idOf(record: CatalogRecord, fields: Field[]): string {
  return String(record[fieldOf(fields, "slug") ?? "id"] ?? "");
}

export function typeOf(record: CatalogRecord, fields: Field[]): string {
  return String(record[fieldOf(fields, "enum") ?? "type"] ?? "");
}

export function parentOf(record: CatalogRecord, fields: Field[]): string | null {
  const value = record[fieldOf(fields, "ref") ?? "parent_id"];
  return value == null ? null : String(value);
}

export function nameOf(record: CatalogRecord, fields: Field[]): string {
  return String(record[nameField(fields)] ?? idOf(record, fields));
}

export const flagsOf = (record: CatalogRecord) => record.flags ?? [];

function csvCell(value: unknown): string {
  if (value == null) return "";
  const text = Array.isArray(value) ? value.join("; ") : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** One column per field plus `flags`; values with commas, quotes, or newlines quoted. */
export function catalogCsv(records: CatalogRecord[], fields: Field[]): string {
  const header = [...fields.map((f) => f.name), "flags"].map(csvCell).join(",");
  const rows = records.map((r) =>
    [...fields.map((f) => csvCell(r[f.name])), csvCell(flagsOf(r))].join(","),
  );
  return [header, ...rows].join("\n");
}

/** The `records` array as `catalog.json` downloads it. */
export const recordsJson = (records: CatalogRecord[]) => JSON.stringify(records, null, 2);

export type Filters = { q: string; types: string[]; flagged: boolean; missing: string };
export const NO_FILTERS: Filters = { q: "", types: [], flagged: false, missing: "" };

/** Records matching the search (name, short value, id), the types, flagged only, and missing. */
export function filterRecords(
  records: CatalogRecord[],
  fields: Field[],
  filters: Filters,
): CatalogRecord[] {
  const needle = filters.q.trim().toLowerCase();
  const short = shortField(fields);
  return records.filter((r) => {
    const text = [nameOf(r, fields), short ? (r[short] ?? "") : "", idOf(r, fields)]
      .join(" ")
      .toLowerCase();
    return (
      (!needle || text.includes(needle)) &&
      (!filters.types.length || filters.types.includes(typeOf(r, fields))) &&
      (!filters.flagged || flagsOf(r).length > 0) &&
      (!filters.missing || r[filters.missing] == null)
    );
  });
}

/** Depth per record ID: levels below a seed, from the ref chain. */
export function depths(records: CatalogRecord[], fields: Field[]): Map<string, number> {
  const parent = new Map(records.map((r) => [idOf(r, fields), parentOf(r, fields)]));
  const out = new Map<string, number>();
  for (const id of parent.keys()) {
    let d = 0;
    let p = parent.get(id);
    const seen = new Set([id]);
    while (p && parent.has(p) && !seen.has(p)) {
      seen.add(p);
      d++;
      p = parent.get(p);
    }
    out.set(id, d);
  }
  return out;
}

/** Records per depth, shallowest first. */
export function byDepth(records: CatalogRecord[], fields: Field[]): [number, number][] {
  const counts = new Map<number, number>();
  for (const d of depths(records, fields).values()) counts.set(d, (counts.get(d) ?? 0) + 1);
  return [...counts].sort((a, b) => a[0] - b[0]);
}

/** The `n` fields with the fewest values, fewest first. */
export function worstFilled(
  records: CatalogRecord[],
  fields: Field[],
  n = 3,
): { field: string; filled: number }[] {
  return fields
    .map((f) => ({ field: f.name, filled: records.filter((r) => r[f.name] != null).length }))
    .sort((a, b) => a.filled - b.filled)
    .slice(0, n);
}

/** The distinct source URLs the records cite. */
export function sourceUrls(records: CatalogRecord[]): string[] {
  return [...new Set(records.flatMap((r) => Object.values(r.sources ?? {})).filter(Boolean))];
}

/** A record's pages: each source URL once, with the fields taken from it. */
export function pagesOf(record: CatalogRecord): { url: string; fields: string[] }[] {
  const pages = new Map<string, string[]>();
  for (const [field, url] of Object.entries(record.sources ?? {}))
    if (url) pages.set(url, [...(pages.get(url) ?? []), field]);
  return [...pages].map(([url, fields]) => ({ url, fields }));
}

export type GraphNode = { id: string; x: number; y: number; record: CatalogRecord };
export type Graph = {
  width: number;
  height: number;
  nodes: GraphNode[];
  edges: { from: string; to: string; d: string }[];
};

export const GRAPH = { row: 24, column: 230, padX: 24, padY: 20, labelRoom: 200 };

/** The tree from the ref field, left to right: leaves one row each, a parent centred on its
 * children; seeds (and records whose parent is missing) are roots. */
export function graphLayout(records: CatalogRecord[], fields: Field[]): Graph {
  const { row, column, padX, padY, labelRoom } = GRAPH;
  const ids = new Set(records.map((r) => idOf(r, fields)));
  const kids = new Map<string | null, CatalogRecord[]>();
  for (const r of records) {
    const p = parentOf(r, fields);
    const key = p && ids.has(p) && p !== idOf(r, fields) ? p : null;
    kids.set(key, [...(kids.get(key) ?? []), r]);
  }
  const pos = new Map<string, { x: number; y: number; record: CatalogRecord }>();
  let next = 0;
  let deepest = 0;
  const place = (r: CatalogRecord, depth: number): number => {
    const id = idOf(r, fields);
    deepest = Math.max(deepest, depth);
    const children = pos.has(id) ? [] : (kids.get(id) ?? []);
    pos.set(id, { x: padX + depth * column, y: 0, record: r });
    let y: number;
    if (!children.length) y = padY + next++ * row;
    else {
      const ys = children.map((c) => place(c, depth + 1));
      y = (Math.min(...ys) + Math.max(...ys)) / 2;
    }
    pos.set(id, { x: padX + depth * column, y, record: r });
    return y;
  };
  for (const r of kids.get(null) ?? []) place(r, 0);
  // Records in a ref cycle reach no root; give each a row of its own.
  for (const r of records) if (!pos.has(idOf(r, fields))) place(r, 0);
  const nodes = [...pos].map(([id, p]) => ({ id, ...p }));
  const edges = nodes.flatMap((n) => {
    const p = parentOf(n.record, fields);
    const a = p ? pos.get(p) : undefined;
    if (!p || !a || p === n.id) return [];
    const mx = (a.x + n.x) / 2;
    return [
      { from: p, to: n.id, d: `M${a.x + 6} ${a.y} C${mx} ${a.y} ${mx} ${n.y} ${n.x - 6} ${n.y}` },
    ];
  });
  return {
    width: padX * 2 + deepest * column + labelRoom,
    height: padY * 2 + Math.max(0, next - 1) * row,
    nodes,
    edges,
  };
}

/** A node's label: the short value, else the name cut to 24 characters. */
export function graphLabel(record: CatalogRecord, fields: Field[]): string {
  const short = shortField(fields);
  const value = short ? record[short] : null;
  if (value != null && value !== "") return String(value);
  const name = nameOf(record, fields);
  return name.length > 24 ? `${name.slice(0, 23)}…` : name;
}

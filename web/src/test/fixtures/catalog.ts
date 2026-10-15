// A catalog run's structure, records, and nodes, after the prototype's `new` (Catalog),
// `live-catalog`, and `catalog-result` scenarios.
import type { Catalog, CatalogNode, CatalogRecord, Structure } from "../../api/types";

export const CATALOG_BRIEF =
  "Every public organization of the Peruvian state, from the three powers down to their attached bodies and offices, as structured records.";

export const TYPES = [
  "power",
  "ministry",
  "autonomous_body",
  "public_body",
  "regional_government",
  "local_government",
  "office",
];

const field = (name: string, type: Structure["fields"][number]["type"], required = false) => ({
  name,
  type,
  required,
  volatile: false,
});

/** The prototype's drafted structure: 12 fields, 6 seeds, depth 3, 200 nodes, 2 pages. */
export const structure: Structure = {
  fields: [
    field("id", "slug", true),
    field("name", "text", true),
    field("acronym", "text"),
    { ...field("type", "enum", true), values: TYPES },
    field("parent_id", "ref"),
    field("head_title", "text"),
    { ...field("head_name", "text"), volatile: true },
    field("verified_on", "date"),
    field("description", "text"),
    field("website", "url"),
    field("gobpe", "url"),
    field("legal_basis", "text"),
  ],
  relation: "organismos públicos adscritos o dependientes",
  seeds: [
    { name: "Poder Ejecutivo", type: "power", url: "https://www.gob.pe/presidencia" },
    { name: "Poder Legislativo", type: "power", url: "https://www.congreso.gob.pe" },
    { name: "Poder Judicial", type: "power", url: "https://www.pj.gob.pe" },
    { name: "PCM", type: "ministry", url: "https://www.gob.pe/pcm" },
    { name: "JNE", type: "autonomous_body", url: null },
    { name: "BCRP", type: "autonomous_body", url: "https://www.bcrp.gob.pe" },
  ],
  leaf_types: ["regional_government", "office"],
  expand: "both",
  limits: { max_depth: 3, max_nodes: 200, pages_per_node: 2 },
  language: "es",
};

const record = (
  id: string,
  name: string,
  type: string,
  parent_id: string | null,
  extra: Record<string, unknown> = {},
  flags: string[] = [],
): CatalogRecord => ({
  id,
  name,
  acronym: null,
  type,
  parent_id,
  head_title: "Titular",
  head_name: null,
  verified_on: "2026-10-15",
  description: null,
  website: null,
  gobpe: `gob.pe/${id}`,
  legal_basis: "Constitución Política",
  ...extra,
  sources: { gobpe: `https://www.gob.pe/${id}`, head_title: `https://www.gob.pe/${id}` },
  flags,
});

export const records: CatalogRecord[] = [
  record("poder-ejecutivo", "Poder Ejecutivo", "power", null),
  record("pcm", "Presidencia del Consejo de Ministros", "ministry", "poder-ejecutivo", {
    acronym: "PCM",
    website: "pcm.gob.pe",
  }),
  record(
    "mef",
    "Ministerio de Economía y Finanzas",
    "ministry",
    "poder-ejecutivo",
    { acronym: "MEF", head_name: "R. Salazar" },
    ["head_name from a source dated 2025-10-02"],
  ),
  record(
    "sunat",
    "Superintendencia Nacional de Aduanas y de Administración Tributaria",
    "public_body",
    "mef",
    {
      acronym: "SUNAT",
      website: "sunat.gob.pe",
      description: 'Tax "and" customs, Peru',
    },
  ),
  record(
    "inei",
    "Instituto Nacional de Estadística e Informática",
    "public_body",
    "pcm",
    {
      acronym: "INEI",
    },
    ["website: only a gob.pe page was found"],
  ),
  record("bcrp", "Banco Central de Reserva del Perú", "autonomous_body", null, {
    acronym: "BCRP",
    website: "bcrp.gob.pe",
  }),
];

export const nodes: CatalogNode[] = [
  ["poder-ejecutivo", "Poder Ejecutivo", "power", null, 0],
  ["pcm", "Presidencia del Consejo de Ministros", "ministry", "poder-ejecutivo", 1],
  ["mef", "Ministerio de Economía y Finanzas", "ministry", "poder-ejecutivo", 1],
  [
    "sunat",
    "Superintendencia Nacional de Aduanas y de Administración Tributaria",
    "public_body",
    "mef",
    2,
  ],
  ["inei", "Instituto Nacional de Estadística e Informática", "public_body", "pcm", 2],
  ["bcrp", "Banco Central de Reserva del Perú", "autonomous_body", null, 0],
].map(([id, name, type, parent_id, depth]) => ({
  id: id as string,
  name: name as string,
  type: type as string,
  parent_id: parent_id as string | null,
  depth: depth as number,
  status: "extracted" as const,
  pages: id === "sunat" ? ["s1", "s2"] : ["s1"],
}));

export const catalog: Catalog = {
  records,
  nodes: 6,
  reason: "frontier empty",
  note: "No unexpanded nodes left after wave 3. Max depth 3 was not reached.",
  waves: [{ wave: 1, expanded: 2, found: 4, records: 2, failed: 0, dropped: 0 }],
  fill: {},
  by_type: {},
  by_depth: { "0": 2, "1": 2, "2": 2 },
};

// Catalog runs: the Structure panel's rules and request, and the live view folded from the
// catalog events (frontier, records, coverage). Pure, like the research reducer.
import type * as G from "../api/generated";
import type {
  CatalogOutput,
  DomainLists,
  FieldType,
  Limits,
  RunCreate,
  RunEvent,
  Structure,
  StructureField,
  WritingOptions,
} from "../api/types";
import { type ProfileChoice, profilePatch } from "./profileValues";
import { KIND_STEPS } from "./thinking";

export const FIELD_TYPES: FieldType[] = ["text", "slug", "url", "date", "enum", "ref"];
export const DEFAULT_LIMITS: Limits = { max_depth: 3, max_nodes: 200, pages_per_node: 2 };

export type LimitKey = keyof Limits;
export const LIMITS: { key: LimitKey; label: string; min: number; max: number }[] = [
  { key: "max_depth", label: "Max depth", min: 1, max: 10 },
  { key: "max_nodes", label: "Max nodes", min: 1, max: 5000 },
  { key: "pages_per_node", label: "Pages per node", min: 1, max: 10 },
];

/** A typed field name: runs of white space become `_`. */
export function fieldName(text: string): string {
  return text.replace(/\s+/g, "_");
}

/** A limit as typed, clamped to its range; NaN (an empty input) stays NaN. */
export function clampLimit(key: LimitKey, value: number): number {
  const range = LIMITS.find((l) => l.key === key);
  if (!range || Number.isNaN(value)) return value;
  return Math.max(range.min, Math.min(range.max, Math.round(value)));
}

export function limitsOf(structure: Structure | null | undefined): Limits {
  return { ...DEFAULT_LIMITS, ...structure?.limits };
}

const num = (n: number) => (Number.isFinite(n) ? n : 0);

/** "Up to 200 nodes · about 400 pages · 200 extraction calls", with " · 1 report" for a report. */
export function estimate(limits: Limits, output: CatalogOutput = "table"): string {
  const nodes = num(limits.max_nodes);
  const pages = nodes * num(limits.pages_per_node);
  const report = wantsReport(output) ? " · 1 report" : "";
  return `Up to ${nodes} nodes · about ${pages} pages · ${nodes} extraction calls${report}`;
}

/** Report and Both write a report from the records; Table does not. */
export function wantsReport(output: CatalogOutput | null | undefined): boolean {
  return output === "report" || output === "both";
}

/** The field holding the node type, whose `values` are the types. */
export function enumField(structure: Pick<Structure, "fields">): StructureField | undefined {
  return structure.fields.find((f) => f.type === "enum");
}

/** The node types: the enum field's values. */
export function typesOf(structure: Pick<Structure, "fields"> | null | undefined): string[] {
  return (structure && enumField(structure)?.values) ?? [];
}

/** The field shown as the record's name: `name`, else the first text field. */
export function nameField(fields: Pick<StructureField, "name" | "type">[]): string {
  return (
    fields.find((f) => f.name === "name")?.name ??
    fields.find((f) => f.type === "text")?.name ??
    "name"
  );
}

/** The acronym-like short value: the second text field, when there is one. */
export function shortField(fields: Pick<StructureField, "name" | "type">[]): string | undefined {
  const name = nameField(fields);
  return fields.filter((f) => f.type === "text" && f.name !== name)[0]?.name;
}

export type CatalogForm = {
  brief: string;
  structure: Structure;
  profile: string;
  /** Lists that differ from their defaults. */
  domains: Partial<DomainLists>;
  choice: ProfileChoice;
  /** The overridden writing fields; sent only when the output wants a report. */
  writing?: Partial<WritingOptions>;
};

/** `POST /api/runs` for a catalog: the brief as `query`, the structure, and the shared fields. */
export function catalogRequest(form: CatalogForm): RunCreate {
  const structure: Structure = {
    ...form.structure,
    language: form.structure.language?.trim() ?? "",
    record_language: form.structure.record_language?.trim() ?? "",
    fields: form.structure.fields.map((f) => ({ ...f, name: fieldName(f.name.trim()) })),
    limits: limitsOf(form.structure),
  };
  const request: RunCreate = {
    query: form.brief.trim(),
    kind: "catalog",
    structure,
    profile: form.profile,
  };
  if (form.writing && wantsReport(structure.output) && Object.keys(form.writing).length) {
    request.writing = form.writing;
  }
  if (Object.keys(form.domains).length) request.domains = form.domains;
  return { ...request, ...profilePatch(form.choice, KIND_STEPS.catalog) };
}

/** The Structure panel rows a server error can name, by the key after `structure.`. */
export const STRUCTURE_ROWS: Record<string, string> = {
  fields: "c-fields",
  relation: "c-rel",
  seeds: "c-seeds",
  leaf_types: "c-leaf",
  expand: "c-expand",
  output: "c-output",
  limits: "c-limits",
  language: "c-lang",
};

/** The row a 422 names (`structure.seeds.0.type`), or null when it names none. */
export function structureRow(fields: Record<string, string>): string | null {
  for (const key of Object.keys(fields)) {
    const match = /^structure\.([a-z_]+)/.exec(key);
    if (match) return STRUCTURE_ROWS[match[1]] ?? "c-fields";
  }
  return null;
}

// ---- Live view -------------------------------------------------------------------------------

export const CATALOG_PHASES = [
  "load",
  "draft",
  "expand",
  "search",
  "fetch",
  "chunk",
  "extract",
  "assemble",
  "write",
] as const;
export type CatalogPhaseId = (typeof CATALOG_PHASES)[number];
export const CATALOG_LOOP: readonly CatalogPhaseId[] = [
  "expand",
  "search",
  "fetch",
  "chunk",
  "extract",
];

export type NodeStatus = "discovered" | "expanding" | "extracted" | "failed";

export type FrontierNode = {
  id: string;
  name: string;
  type: string;
  parentId: string | null;
  depth: number;
  url: string | null;
  wave: number;
  status: NodeStatus;
  /** From `node.extracted`. */
  children: number | null;
  record: Record<string, unknown> | null;
  sources: Record<string, string>;
  flags: string[];
};

export type CatalogPhase = {
  state: "pending" | "running" | "done" | "failed" | "cancelled";
  /** Summed `stage.done` counts over the waves. */
  count: number;
  /** Summed `stage.done` seconds over the waves. */
  seconds: number;
  startedTs?: string;
  progress?: { done: number; total: number };
};

export type CatalogLive = {
  fields: G.StructureFieldInfo[];
  seeds: number;
  relation: string;
  limits: Limits;
  nodes: Record<string, FrontierNode>;
  /** Node IDs in discovery order. */
  order: string[];
  /** Extracted node IDs, newest first, with the event time. */
  records: { id: string; ts: string }[];
  failed: number;
  /** The wave running (or last run). */
  wave: number;
  wavesDone: number;
  pages: number;
  done: G.CatalogDoneData | null;
  phases: Record<CatalogPhaseId, CatalogPhase>;
};

export function initialCatalog(): CatalogLive {
  const phases = {} as Record<CatalogPhaseId, CatalogPhase>;
  for (const id of CATALOG_PHASES) phases[id] = { state: "pending", count: 0, seconds: 0 };
  return {
    fields: [],
    seeds: 0,
    relation: "",
    limits: DEFAULT_LIMITS,
    nodes: {},
    order: [],
    records: [],
    failed: 0,
    wave: 0,
    wavesDone: 0,
    pages: 0,
    done: null,
    phases,
  };
}

const isCatalogPhase = (stage: string | null | undefined): stage is CatalogPhaseId =>
  !!stage && (CATALOG_PHASES as readonly string[]).includes(stage);

function withPhase(
  state: CatalogLive,
  stage: string | null | undefined,
  patch: Partial<CatalogPhase>,
) {
  if (!isCatalogPhase(stage)) return state;
  return { ...state, phases: { ...state.phases, [stage]: { ...state.phases[stage], ...patch } } };
}

function withNode(state: CatalogLive, id: string, patch: Partial<FrontierNode>): CatalogLive {
  const node = state.nodes[id];
  if (!node) return state;
  return { ...state, nodes: { ...state.nodes, [id]: { ...node, ...patch } } };
}

function stopRunning(state: CatalogLive, to: CatalogPhase["state"]): CatalogLive {
  const phases = { ...state.phases };
  for (const id of CATALOG_PHASES)
    if (phases[id].state === "running") phases[id] = { ...phases[id], state: to };
  return { ...state, phases };
}

/** Folds one event into the catalog view; events of research runs leave it unchanged. */
export function catalogReducer(state: CatalogLive, event: RunEvent): CatalogLive {
  switch (event.type) {
    case "structure.ready": {
      const d = event.data;
      return {
        ...state,
        fields: d.fields,
        seeds: d.seeds,
        relation: d.relation,
        limits: { ...DEFAULT_LIMITS, ...d.limits },
      };
    }
    case "stage.started": {
      const wave = event.data.round ?? 1;
      let next = withPhase(state, event.stage, {
        state: "running",
        startedTs: event.ts,
        progress: undefined,
      });
      if (event.stage === "expand") {
        // A wave expands every node discovered so far.
        const nodes = { ...next.nodes };
        for (const id of next.order)
          if (nodes[id].status === "discovered") nodes[id] = { ...nodes[id], status: "expanding" };
        next = { ...next, nodes, wave: Math.max(next.wave, wave) };
      } else if (isCatalogPhase(event.stage) && CATALOG_LOOP.includes(event.stage)) {
        next = { ...next, wave: Math.max(next.wave, wave) };
      }
      return next;
    }
    case "stage.progress": {
      const { done, total } = event.data;
      return withPhase(state, event.stage, { progress: { done, total } });
    }
    case "stage.done": {
      if (!isCatalogPhase(event.stage)) return state;
      const phase = state.phases[event.stage];
      return withPhase(state, event.stage, {
        state: "done",
        count: phase.count + (event.data.count ?? 0),
        seconds: phase.seconds + (event.data.skipped ? 0 : (event.data.seconds ?? 0)),
        startedTs: undefined,
      });
    }
    case "stage.failed":
      return withPhase(state, event.stage, { state: "failed" });
    case "page.fetched":
      return event.stage === "load" ? state : { ...state, pages: state.pages + 1 };
    case "node.found": {
      const d = event.data;
      if (state.nodes[d.node_id]) return state;
      const node: FrontierNode = {
        id: d.node_id,
        name: d.name,
        type: d.type,
        parentId: d.parent_id,
        depth: d.depth,
        url: d.url,
        wave: d.wave,
        status: "discovered",
        children: null,
        record: null,
        sources: {},
        flags: [],
      };
      return {
        ...state,
        nodes: { ...state.nodes, [d.node_id]: node },
        order: [...state.order, d.node_id],
      };
    }
    case "node.extracted": {
      const d = event.data;
      if (!state.nodes[d.node_id]) return state;
      const next = withNode(state, d.node_id, {
        status: "extracted",
        record: d.record,
        sources: d.sources ?? {},
        flags: d.flags ?? [],
        children: d.children ?? 0,
      });
      const records = [
        { id: d.node_id, ts: event.ts },
        ...state.records.filter((r) => r.id !== d.node_id),
      ];
      return { ...next, records };
    }
    case "node.failed": {
      const known = state.nodes[event.data.node_id];
      if (!known || known.status === "failed") return state;
      return {
        ...withNode(state, event.data.node_id, { status: "failed" }),
        failed: state.failed + 1,
      };
    }
    case "wave.done":
      return { ...state, wavesDone: Math.max(state.wavesDone, event.data.wave) };
    case "catalog.done":
      return { ...state, done: event.data, wavesDone: event.data.waves };
    case "run.failed":
      return stopRunning(state, "cancelled");
    case "run.cancelled":
      return stopRunning(state, "cancelled");
    default:
      return state;
  }
}

/** A record's value per field: the slug from the node ID, the ref from its parent, the enum from
 * its type, the rest from the extracted record. */
export function nodeValues(
  node: FrontierNode,
  fields: Pick<StructureField, "name" | "type">[],
): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.type === "slug") values[f.name] = node.id;
    else if (f.type === "enum") values[f.name] = node.type;
    else if (f.type === "ref") values[f.name] = node.parentId;
    else values[f.name] = node.record?.[f.name] ?? null;
  }
  return values;
}

/** Percent of `records` with a non-null value per field, lowest first. */
export function fillPercents(
  records: Record<string, unknown>[],
  fields: string[],
): { field: string; pct: number }[] {
  return fields
    .map((field) => {
      const filled = records.filter((r) => r[field] != null && r[field] !== "").length;
      return { field, pct: records.length ? Math.round((filled / records.length) * 100) : 0 };
    })
    .sort((a, b) => a.pct - b.pct);
}

/** Extracted records, newest first. */
export function liveRecords(live: CatalogLive): FrontierNode[] {
  return live.records.map((r) => live.nodes[r.id]).filter(Boolean);
}

export type TreeRow = { node: FrontierNode; level: number; hasChildren: boolean };

/** The frontier as rows, depth first in discovery order; children of closed nodes are left out. */
export function frontierRows(
  live: CatalogLive,
  closed: ReadonlySet<string> = new Set(),
): TreeRow[] {
  const kids = new Map<string | null, string[]>();
  for (const id of live.order) {
    const node = live.nodes[id];
    const parent = node.parentId && live.nodes[node.parentId] ? node.parentId : null;
    kids.set(parent, [...(kids.get(parent) ?? []), id]);
  }
  const rows: TreeRow[] = [];
  const walk = (parent: string | null, level: number) => {
    for (const id of kids.get(parent) ?? []) {
      const hasChildren = (kids.get(id)?.length ?? 0) > 0;
      rows.push({ node: live.nodes[id], level, hasChildren });
      if (hasChildren && !closed.has(id)) walk(id, level + 1);
    }
  };
  walk(null, 0);
  return rows;
}

/** Known nodes per type, most first. */
export function nodesByType(live: CatalogLive): [string, number][] {
  const counts = new Map<string, number>();
  for (const id of live.order) {
    const type = live.nodes[id].type;
    counts.set(type, (counts.get(type) ?? 0) + 1);
  }
  return [...counts].sort((a, b) => b[1] - a[1]);
}

export function countStatus(live: CatalogLive, status: NodeStatus): number {
  return live.order.filter((id) => live.nodes[id].status === status).length;
}

export const CATALOG_PHASE_LABELS: Record<CatalogPhaseId, string> = {
  load: "Load",
  draft: "Draft",
  expand: "Expand",
  search: "Search",
  fetch: "Fetch",
  chunk: "Chunk",
  extract: "Extract",
  assemble: "Assemble",
  write: "Write",
};

export type PhaseCard = {
  id: CatalogPhaseId;
  label: string;
  state: CatalogPhase["state"];
  text: string;
  /** Seconds so far; null before the phase starts. */
  seconds: number | null;
  /** "wave 3" while the loop runs, "5 waves" once it is done; empty outside the loop. */
  loop: string;
  pct: number;
};

const n = (value: number) => value.toLocaleString("en-US");

/** The eight phase cards: state, detail text, time, wave counter, and bar; with `write` (its
 * detail text) a ninth Write card for a run that writes a report. */
export function phaseCards(live: CatalogLive, now: number, write?: string): PhaseCard[] {
  const loopOver = live.phases.assemble.state !== "pending" || !!live.done;
  const expanding = countStatus(live, "expanding");
  const flagged = live.done?.flagged ?? 0;
  const texts: Record<CatalogPhaseId, string> = {
    load: live.phases.load.state === "pending" ? "" : "brief · schema",
    draft: live.fields.length ? `${live.fields.length} fields · ${live.seeds} seeds` : "",
    expand: live.done
      ? `${n(live.done.waves)} waves · ${live.done.reason}`
      : `${n(expanding)} nodes expanding`,
    search: `${n(live.phases.search.count)} queries`,
    fetch: `${n(live.pages)} pages`,
    chunk: `${n(live.phases.chunk.count)} chunks`,
    extract: `${n(live.records.length)} records`,
    assemble: live.done
      ? `${n(live.done.records)} records · ${n(flagged)} flagged`
      : "after the last wave",
    write: write ?? "",
  };
  const ids = CATALOG_PHASES.filter((id) => id !== "write" || write !== undefined);
  return ids.map((id) => {
    const phase = live.phases[id];
    const loop = CATALOG_LOOP.includes(id);
    // Between waves a loop stage that finished its wave is still part of the running loop.
    // `catalog.done` ends every phase before Write, whatever `stage.done` is still on its way.
    const state: CatalogPhase["state"] =
      live.done && id !== "write" && (phase.state === "running" || phase.state === "pending")
        ? "done"
        : loop && phase.state === "done" && !loopOver
          ? "running"
          : phase.state;
    const running = phase.startedTs ? Math.max(0, (now - Date.parse(phase.startedTs)) / 1000) : 0;
    const seconds = state === "pending" ? null : phase.seconds + running;
    const pct =
      state === "done"
        ? 100
        : state === "running"
          ? phase.progress?.total
            ? Math.round((phase.progress.done / phase.progress.total) * 100)
            : 50
          : 0;
    const waves = live.done?.waves ?? live.wavesDone;
    const loopText =
      !loop || state === "pending"
        ? ""
        : loopOver
          ? `${waves} ${waves === 1 ? "wave" : "waves"}`
          : `wave ${Math.max(1, live.wave)}`;
    const pending = state === "pending" && id !== "assemble";
    return {
      id,
      label: CATALOG_PHASE_LABELS[id],
      state,
      text: pending ? "" : texts[id],
      seconds,
      loop: loopText,
      pct,
    };
  });
}

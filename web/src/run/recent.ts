// New run's Recent & pinned list: the groups built from `GET /api/runs`, the names and pins kept
// in browser storage, and the New run draft a row fills in.
import type {
  DepthInfo,
  ProfileInfo,
  RunCreate,
  RunSummary,
  TokenBudget,
  WritingOptions,
} from "../api/types";
import { type Draft, EMPTY_DRAFT, type RunOptions } from "../app/context";
import { shortDate } from "../format";
import { depthLabel, researchOf } from "./depth";
import { recipeOf } from "./format";
import type { ProfileEdits } from "./profileValues";

export const RECENT_LIMIT = 20;
const NAMES_KEY = "wosarcher-run-names";
const PINS_KEY = "wosarcher-run-pins";

/** An attachment taken from an earlier run: sent by name, never uploaded again. */
export type ReusedFile = { runId: string; runName: string; name: string; size: number };

/** The user's names (by run ID) and pins (in the order pinned). */
export type Marks = { names: Record<string, string>; pins: string[] };

export type RecentRow = { run: RunSummary; count: number };
export type RecentGroups = { pinned: RunSummary[]; recent: RecentRow[] };

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function loadMarks(): Marks {
  const names = read<Record<string, string>>(NAMES_KEY, {});
  const pins = read<string[]>(PINS_KEY, []);
  return {
    names: names && typeof names === "object" && !Array.isArray(names) ? names : {},
    pins: Array.isArray(pins) ? pins.filter((id) => typeof id === "string") : [],
  };
}

export function saveMarks(marks: Marks): void {
  try {
    localStorage.setItem(NAMES_KEY, JSON.stringify(marks.names));
    localStorage.setItem(PINS_KEY, JSON.stringify(marks.pins));
  } catch {
    // Storage may be full or blocked; names and pins then last for this page only.
  }
}

/** Drops names and pins of runs the server no longer lists. */
export function pruneMarks(marks: Marks, runs: RunSummary[]): Marks {
  const ids = new Set(runs.map((r) => r.run_id));
  return {
    names: Object.fromEntries(Object.entries(marks.names).filter(([id]) => ids.has(id))),
    pins: marks.pins.filter((id) => ids.has(id)),
  };
}

export const togglePin = (marks: Marks, id: string): Marks => ({
  ...marks,
  pins: marks.pins.includes(id) ? marks.pins.filter((p) => p !== id) : [...marks.pins, id],
});

/** An empty name or the question itself removes the custom name. */
export function rename(marks: Marks, run: RunSummary, value: string): Marks {
  const { [run.run_id]: _, ...names } = marks.names;
  const name = value.trim();
  return { ...marks, names: name && name !== run.query ? { ...names, [run.run_id]: name } : names };
}

export const rowName = (run: RunSummary, names: Record<string, string>) =>
  names[run.run_id] || run.query;

/** JSON with object keys sorted, so equal forms give equal text. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : 1));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

/** Runs with this key collapse into one row: question, options, and attachment names. */
export function duplicateKey(run: RunSummary): string {
  const options = run.form ?? {
    depth: run.depth,
    sources: run.sources,
    until: run.until,
    profile: run.profile,
    writing: run.writing,
  };
  return canonical([run.query, options, (run.attachments ?? []).map((a) => a.name)]);
}

/** Pinned runs in pin order, then the newest runs that are not forks, duplicates collapsed. */
export function recentGroups(runs: RunSummary[], pins: string[]): RecentGroups {
  const byId = new Map(runs.map((r) => [r.run_id, r]));
  const pinned = pins.flatMap((id) => byId.get(id) ?? []);
  const rows = new Map<string, RecentRow>();
  const newest = [...runs].sort((a, b) => (a.created < b.created ? 1 : -1));
  for (const run of newest) {
    if (run.parent_run_id || pins.includes(run.run_id)) continue;
    const key = duplicateKey(run);
    const row = rows.get(key);
    if (row) row.count += 1;
    else rows.set(key, { run, count: 1 });
  }
  return { pinned, recent: [...rows.values()].slice(0, RECENT_LIMIT) };
}

/** "<Depth> · <recipe> · <sources> · <profile or custom (profile)> · <N> words". */
export function rowSummary(run: RunSummary): string {
  return [
    depthLabel(run.depth),
    recipeOf(run.until, run.writing.format),
    run.sources,
    run.modified ? `custom (${run.profile})` : run.profile,
    `${run.writing.words} words`,
  ].join(" · ");
}

/** "Just now", "12m ago", "3h ago", else the date. */
export function relativeDate(iso: string, now = Date.now()): string {
  const minutes = Math.floor((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)}h ago`;
  return shortDate(iso);
}

/** The Advanced edits a request's `llm` carries, as the profile control holds them. */
function editsOf(llm: RunCreate["llm"]): ProfileEdits {
  const edits: ProfileEdits = {};
  if (!llm) return edits;
  if (llm.model) edits.model = llm.model;
  if (llm.context_window != null) edits.context_window = llm.context_window;
  if (llm.max_output_tokens != null) edits.max_output_tokens = llm.max_output_tokens;
  if (llm.context_tokens != null) edits.context_tokens = llm.context_tokens as TokenBudget;
  if (llm.gap_context_tokens != null)
    edits.gap_context_tokens = llm.gap_context_tokens as TokenBudget;
  for (const step of ["plan", "gap", "write"] as const) {
    const level = llm.reasoning?.[step];
    if (level) edits[step] = level;
  }
  return edits;
}

type Known = {
  profiles: ProfileInfo[];
  depths: DepthInfo[];
  /** The global writing defaults; Custom's Length falls back to them. */
  saved?: WritingOptions;
};

/**
 * The New run draft a row fills in: from the run's `form`, else from its summary. A profile or
 * depth that no longer exists falls back to the active profile (no override) and Standard.
 */
export function draftFromRun(run: RunSummary, name: string, known: Known): Draft {
  const form = run.form;
  const profileKnown = known.profiles.some((p) => p.name === (form?.profile ?? run.profile));
  const requested = form ? form.depth : run.depth;
  const depth =
    requested === "custom" || known.depths.some((d) => d.name === requested)
      ? (requested ?? "standard")
      : "standard";
  const { format, words, ...writing } = form?.writing ?? {};
  const options: Partial<RunOptions> = {
    recipe: recipeOf(form ? form.until : run.until, form ? format : run.writing.format),
    depth,
  };
  const sources = form ? form.sources : run.sources;
  if (sources) options.sources = sources;
  if (profileKnown) options.profile = form?.profile ?? run.profile;
  const draft: Draft = {
    ...EMPTY_DRAFT,
    query: run.query,
    options,
    reused: (run.attachments ?? []).map((a) => ({ runId: run.run_id, runName: name, ...a })),
  };
  if (!form) return draft;
  const filled: Draft = {
    ...draft,
    writing: { ...writing } as Partial<WritingOptions>,
    domains: {
      ...(form.domains?.allow ? { allow: form.domains.allow } : {}),
      ...(form.domains?.block ? { block: form.domains.block } : {}),
    },
    searchLanguage: form.search_language ?? "",
    use: profileKnown ? { ...(form.use ?? {}) } : {},
    profileEdits: profileKnown ? editsOf(form.llm) : {},
  };
  if (depth === "custom") {
    const standard = known.depths.find((d) => d.name === "standard");
    const base = standard ? researchOf(standard) : undefined;
    const values = { ...base, ...form.research } as ReturnType<typeof researchOf>;
    const length = words ?? known.saved?.words ?? standard?.values.words ?? 0;
    return { ...filled, custom: { values, words: length } };
  }
  return words != null ? { ...filled, writing: { ...filled.writing, words } } : filled;
}

/** What the "from" chip compares: the draft's question and options, files by name. */
export function draftSignature(draft: Draft): string {
  return canonical({
    ...draft,
    query: draft.query.trim(),
    files: draft.files.map((f) => f.name),
  });
}

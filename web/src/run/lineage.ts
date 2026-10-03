// The versions of one run (its lineage) from the GET /api/runs list: the root and every fork
// whose parent chain reaches it.
import type { RunSummary } from "../api/types";
import { fmtElapsed, wDiff } from "./format";

export type Version = {
  run: RunSummary;
  kind: string;
  description: string;
  current: boolean;
};

function rootOf(byId: Map<string, RunSummary>, run: RunSummary): RunSummary {
  let current = run;
  const seen = new Set([run.run_id]);
  while (current.parent_run_id) {
    const parent = byId.get(current.parent_run_id);
    if (!parent || seen.has(parent.run_id)) break;
    seen.add(parent.run_id);
    current = parent;
  }
  return current;
}

const duration = (run: RunSummary) => (run.duration_s == null ? "–" : fmtElapsed(run.duration_s));

export function kindOf(run: RunSummary): string {
  if (!run.parent_run_id) return "research";
  return run.fork_from === "write" ? "rewrite" : `fork from ${run.fork_from}`;
}

/** Oldest first (by version, then creation); empty when `id` is not in `runs`. */
export function lineage(runs: RunSummary[], id: string): Version[] {
  const byId = new Map(runs.map((r) => [r.run_id, r]));
  const viewed = byId.get(id);
  if (!viewed) return [];
  const root = rootOf(byId, viewed);
  const members = runs.filter((r) => rootOf(byId, r).run_id === root.run_id);
  members.sort((a, b) => (a.version ?? 1) - (b.version ?? 1) || a.created.localeCompare(b.created));
  return members.map((run) => {
    const parent = run.parent_run_id ? byId.get(run.parent_run_id) : undefined;
    const changes = parent ? wDiff(parent.writing, run.writing) || "same options" : "full run";
    return {
      run,
      kind: kindOf(run),
      description: `${changes} · ${duration(run)}`,
      current: run.run_id === id,
    };
  });
}

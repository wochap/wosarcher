// Display scores (0 to 1) as the server maps them, and the passages of a run that were not
// kept, which only its `scores.jsonl` and `chunks.jsonl` artifacts hold.
import type { Chunk, Score } from "../api/generated";
import type { KeptPassage } from "../api/types";

const JEV_MAX = 3;
const clamp = (x: number) => Math.min(1, Math.max(0, x));

/** `best` is the best raw value of the same query (for `bm25`); `passthrough` has no score. */
export function displayScore(scorer: string, value: number, best: number): number | null {
  if (scorer === "passthrough") return null;
  if (scorer === "jev") return clamp(value / JEV_MAX);
  if (scorer === "bm25") return best > 0 ? clamp(value / best) : 0;
  return clamp(value);
}

/** One passage card of the Passages panel, kept or not. */
export type PassageItem = KeptPassage & {
  queryId: string;
  scorer: string;
  threshold: number | null;
  kept: boolean;
  /** Why the pair was not kept; null for kept pairs and runs from before drop reasons. */
  dropped?: Score["dropped"];
};

export function parseJsonl<T>(text: string): T[] {
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as T);
}

/**
 * One card per chunk not kept by any query, from its pair with the best display, carrying that
 * pair's drop reason. `thresholds` maps a query to its scorer's display threshold.
 */
export function notKeptPassages(
  scores: Score[],
  chunks: Chunk[],
  thresholds: Record<string, number | null>,
  sources: Record<string, { title: string; uri: string }>,
): PassageItem[] {
  const best: Record<string, number> = {};
  for (const s of scores) best[s.query_id] = Math.max(best[s.query_id] ?? 0, s.value);
  const kept = new Set(scores.filter((s) => s.kept).map((s) => s.chunk_id));
  const byChunk = new Map(chunks.map((c) => [c.chunk_id, c]));
  const out = new Map<string, PassageItem>();
  for (const s of scores) {
    const chunk = byChunk.get(s.chunk_id);
    if (s.kept || kept.has(s.chunk_id) || !chunk) continue;
    const display = s.display ?? displayScore(s.scorer, s.value, best[s.query_id] ?? 0);
    const current = out.get(s.chunk_id);
    if (current && (current.display ?? 0) >= (display ?? 0)) continue;
    const source = sources[chunk.source_id];
    out.set(s.chunk_id, {
      chunk_id: chunk.chunk_id,
      source_id: chunk.source_id,
      heading_path: chunk.heading_path ?? [],
      text: chunk.text,
      title: source?.title ?? "",
      uri: source?.uri ?? "",
      display,
      queryId: s.query_id,
      scorer: s.scorer,
      threshold: thresholds[s.query_id] ?? null,
      kept: false,
      dropped: s.dropped,
    });
  }
  return [...out.values()];
}

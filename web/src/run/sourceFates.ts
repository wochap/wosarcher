// The Source dialog's words for a chunk's fate: the badge it maps to, the "why" line, and the
// per-sub-query chip text. The server computes every fate; this only formats it.
import type { ChunkFate, ChunkQueryFate, SourceView } from "../api/types";
import type { Fate } from "./fates";

const fixed = (n: number) => n.toFixed(2);

const BADGES: Record<ChunkFate["kind"], Fate> = {
  cited: "cited",
  kept: "kept",
  source_cap: "srccap",
  budget: "budget",
  query_cap: "qcap",
  below_threshold: "below",
  prefiltered: "pre",
  pending: "pending",
};

export const badgeOf = (fate: ChunkFate): Fate => BADGES[fate.kind];

/**
 * Why the chunk ended where it did. `cite` turns a citation number into the run's marker label;
 * `prefilterTopK` is the run's `prefilter.top_k`, when known.
 */
export function whyLine(
  fate: ChunkFate,
  view: Pick<SourceView, "threshold" | "query_cap" | "source_cap">,
  cite: (n: number) => string,
  prefilterTopK?: number,
): string {
  const q = fate.query_id ?? "";
  const score = fate.display == null ? "–" : fixed(fate.display);
  const threshold = view.threshold == null ? "the" : `the ${fixed(view.threshold)}`;
  const above = view.threshold == null ? "the threshold" : fixed(view.threshold);
  const kept = `Kept: rank ${fate.rank ?? "–"} of ${fate.kept_in_query ?? "–"} in ${q}`;
  switch (fate.kind) {
    case "prefiltered":
      return prefilterTopK
        ? `Not scored: outside the top ${prefilterTopK} for every sub-query.`
        : "Not scored: outside the prefilter's top passages for every sub-query.";
    case "pending":
      return "Waiting for the scorer.";
    case "below_threshold":
      return `Scored ${score} in ${q}, below ${threshold} threshold.`;
    case "query_cap":
      return `Scored ${score} in ${q} but ranked ${fate.rank ?? "–"} of ${fate.ranked ?? "–"} above ${above}; ${q} keeps only its top ${view.query_cap}.`;
    case "kept":
      return `${kept}. Selection is running.`;
    case "cited":
      return `${kept}; cited as ${fate.n == null ? "–" : cite(fate.n)}.`;
    case "source_cap":
      return `${kept}; not cited: this source already has ${view.source_cap} cited passages (cap ${view.source_cap} per source).`;
    case "budget":
      return `${kept}; not cited: needs ${fate.tokens_needed ?? "–"} tokens, ${fate.tokens_left ?? "–"} were left in the budget.`;
  }
}

/** A sub-query chip's state text; `other_query` names the query that kept the chunk. */
export function chipText(
  row: ChunkQueryFate,
  fate: ChunkFate,
  threshold: number | null | undefined,
) {
  switch (row.state) {
    case "kept":
      return "kept";
    case "query_cap":
      return "query cap";
    case "below_threshold":
      return threshold == null ? "below threshold" : `below ${fixed(threshold)}`;
    case "other_query":
      return `counted in ${fate.query_id ?? "another"}`;
    case "prefiltered":
      return "prefiltered";
    case "not_in_results":
      return "not in results";
    case "pending":
      return "pending";
  }
}

// The fate of a passage card: why it was cited, is still waiting, or was left out.
import type { Context, SelectSkip } from "../api/generated";
import type { RunView } from "./reducer";
import type { PassageItem } from "./scores";

export type Fate = "cited" | "kept" | "above" | "srccap" | "budget" | "qcap" | "below";

/**
 * The fates the Kept filter lists. "above" is left out: which passages are kept is known only
 * once score is done, so before that the Kept filter is empty and points to All.
 */
export const KEPT_FATES: ReadonlySet<Fate> = new Set(["cited", "kept", "srccap", "budget"]);

const finished = (run: RunView, phase: "score" | "select") =>
  run.phases[phase].state === "done" || run.phases[phase].state === "reused";

/**
 * A kept card is "above" until score is done, then "kept" until select is done, then cited or
 * skipped; without `select.jsonl` (older runs) it stays "kept". A card that was not kept takes
 * its pair's drop reason; a missing reason counts as the threshold.
 */
export function fateOf(
  card: PassageItem,
  run: RunView,
  context: Context | null,
  skips: SelectSkip[] | null,
): Fate {
  if (!card.kept) return card.dropped === "query_cap" ? "qcap" : "below";
  if (!finished(run, "score")) return "above";
  if (!finished(run, "select")) return "kept";
  if (context?.passages.some((p) => p.chunk_id === card.chunk_id)) return "cited";
  const skip = skips?.find((s) => s.chunk_id === card.chunk_id);
  if (skip) return skip.reason === "source_cap" ? "srccap" : "budget";
  return "kept";
}

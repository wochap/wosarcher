// Display formats of the run screens, after the prototype's fmtT, fmtK, fmtB, wSum, and wDiff.
import type { RunSummary, WritingOptions } from "../api/types";
import { describeValue, type WritingField } from "../components/WritingOptionsForm";
import { minSec } from "../format";

/** Seconds as m:ss: 125 → "2:05". */
export const fmtElapsed = minSec;

/** 1234 → "1.2k", 999 → "999". */
export function fmtK(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

/** 512 → "512 B", 4403 → "4.3 KB". */
export function fmtBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

/** 0.0024 → "$0.0024"; zero → "$0.0000 · local". */
export function fmtCost(cost: number): string {
  return cost ? `$${cost.toFixed(4)}` : "$0.0000 · local";
}

/** "Analytical · 1200 words · English · [1] Numeric". */
export function wSummary(w: WritingOptions): string {
  return [
    describeValue("tone", w.tone),
    describeValue("words", w.words),
    describeValue("language", w.language),
    describeValue("citation_marker", w.citation_marker),
    w.reference_style,
  ].join(" · ");
}

/** The Report options line of an answer: "Answer, at most 400 words · Objective · English · …". */
export function aSummary(w: WritingOptions): string {
  return [
    `Answer, at most ${w.words} words`,
    describeValue("tone", w.tone),
    describeValue("language", w.language),
    describeValue("citation_marker", w.citation_marker),
    w.reference_style,
  ].join(" · ");
}

/** The writing options in which `next` differs from `base`: "Concise · 300 words". */
/** A catalog summary may carry no writing options; research screens fall back to these. */
export const DEFAULT_WRITING: WritingOptions = {
  format: "report",
  tone: "objective",
  tone_instructions: "",
  words: 1200,
  language: "english",
  citation_marker: "numeric",
  reference_style: "APA",
};

/** Nothing differs when either run has no writing options (a catalog run). */
export function wDiff(base: WritingOptions | null, next: WritingOptions | null): string {
  if (!base || !next) return "";
  const fields = Object.keys(next) as WritingField[];
  return fields
    .filter((f) => String(base[f]) !== String(next[f]))
    .map((f) => (f === "tone_instructions" ? "custom instructions" : describeValue(f, next[f])))
    .join(" · ");
}

/** "model gemma-3-12b" when the run's model or llm entry differs from its parent's, else "". */
export function modelDiff(
  parent: Pick<RunSummary, "model" | "use">,
  run: Pick<RunSummary, "model" | "use">,
): string {
  const changed = parent.model !== run.model || parent.use?.llm !== run.use?.llm;
  return changed && run.model ? `model ${run.model}` : "";
}

export type Recipe = "report" | "answer" | "context";

/** A run's recipe: `context` when it stops at select, else its writing format. */
export function recipeOf(
  until: string | null | undefined,
  format: string | null | undefined,
): Recipe {
  if (until === "select") return "context";
  return format === "answer" ? "answer" : "report";
}

// Display formats of the run screens, after the prototype's fmtT, fmtK, fmtB, wSum, and wDiff.
import type { WritingOptions } from "../api/types";
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

/** The writing options in which `next` differs from `base`: "Concise · 300 words". */
export function wDiff(base: WritingOptions, next: WritingOptions): string {
  const fields = Object.keys(next) as WritingField[];
  return fields
    .filter((f) => String(base[f]) !== String(next[f]))
    .map((f) => (f === "tone_instructions" ? "custom instructions" : describeValue(f, next[f])))
    .join(" · ");
}

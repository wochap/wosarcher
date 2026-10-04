// Choices for the writing options (docs/design.md, "Writing options").
import type { WritingOptions } from "../api/types";

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** The 11 tones with the prototype's one-line descriptions. */
export const TONES: { value: string; label: string; description: string }[] = [
  ["objective", "neutral and evidence-first"],
  ["formal", "precise, impersonal register"],
  ["analytical", "breaks the question into causes and factors"],
  ["persuasive", "argues for a recommendation"],
  ["informative", "a plain, broad overview"],
  ["explanatory", "teaches how and why, step by step"],
  ["descriptive", "a detailed account of what exists"],
  ["critical", "weighs strengths, weaknesses and gaps"],
  ["comparative", "sets the options side by side"],
  ["speculative", "explores likely futures and open questions"],
  ["reflective", "considers implications and trade-offs"],
].map(([value, description]) => ({ value, label: capitalize(value), description }));

export const LANGUAGES = [
  "English",
  "German",
  "French",
  "Spanish",
  "Portuguese",
  "Japanese",
  "Chinese (Simplified)",
];

export const CITATION_MARKERS: { value: WritingOptions["citation_marker"]; label: string }[] = [
  { value: "numeric", label: "[1] Numeric" },
  { value: "superscript", label: "¹ Superscript" },
  { value: "author-year", label: "(Author, year)" },
];

export const REFERENCE_STYLES = ["APA", "MLA", "Chicago", "IEEE"];

/** The choices plus `current` when it is not among them, so a saved value always shows. */
export function withCurrent(values: string[], current: string): string[] {
  return values.some((v) => v.toLowerCase() === current.toLowerCase())
    ? values
    : [...values, current];
}

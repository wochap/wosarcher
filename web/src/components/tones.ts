// Choices for the writing options (docs/design.md, "Writing options").
import type { WritingOptions } from "../api/types";

export const TONES = [
  "objective",
  "formal",
  "analytical",
  "persuasive",
  "informative",
  "explanatory",
  "descriptive",
  "critical",
  "comparative",
  "speculative",
  "reflective",
];

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

export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** The choices plus `current` when it is not among them, so a saved value always shows. */
export function withCurrent(values: string[], current: string): string[] {
  return values.some((v) => v.toLowerCase() === current.toLowerCase())
    ? values
    : [...values, current];
}

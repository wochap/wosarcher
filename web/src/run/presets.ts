// Saving profiles and depth presets from New run: the name rule (as the server checks it) and
// the generated depth description.
import type { DepthSaveValues } from "../api/types";
import { fmtN } from "./depth";

export type PresetKind = "depth" | "profile";

const BUILTIN_DEPTHS = ["quick", "standard", "deep", "exhaustive"];
const MAX_NAME = 64;

/** Why `name` cannot be saved, or "" when it can; `existing` are the names of that kind. */
export function nameError(name: string, kind: PresetKind, existing: string[]): string {
  const value = name.trim();
  if (!value) return "Enter a name.";
  if (value.length > MAX_NAME) return "Use 64 characters or fewer.";
  if (!/^[A-Za-z0-9_-]+$/.test(value)) return "Use letters, digits, - and _ only.";
  if (!/^[A-Za-z0-9]/.test(value)) return "Start with a letter or digit.";
  const lower = value.toLowerCase();
  if (lower === "custom") return `“${value}” is reserved.`;
  if (kind === "depth" && BUILTIN_DEPTHS.includes(lower))
    return `“${value}” is reserved for a built-in depth.`;
  if (existing.some((e) => e.toLowerCase() === lower))
    return `A ${kind} named “${value}” already exists.`;
  return "";
}

/** "Your preset: <S> sub-queries, <R> round(s), <W> words." */
export function depthDescription(values: DepthSaveValues): string {
  const rounds = `${values.rounds} round${values.rounds === 1 ? "" : "s"}`;
  const words = values.words == null ? "" : `, ${fmtN(values.words)} words`;
  return `Your preset: ${values.sub_queries} sub-queries, ${rounds}${words}.`;
}

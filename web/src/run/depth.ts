// Depth presets in the UI: labels, the effective context budgets, the estimate line, and the
// Custom values remembered in browser storage.
import type { DepthInfo, ProfileInfo, ResearchValues, TokenBudget } from "../api/types";

export type Depth = "quick" | "standard" | "deep" | "exhaustive" | "custom";

export const DEPTH_LABELS: Record<Depth, string> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
  exhaustive: "Exhaustive",
  custom: "Custom",
};

export const CUSTOM_DESCRIPTION = "Set every value yourself.";
const CUSTOM_KEY = "wosarcher-depth-custom";
const MIN_OUTPUT_TOKENS = 1024;
/** Output tokens the gap step's answer reserves, as the server computes it. */
const GAP_OUTPUT_TOKENS = 768;

/** The tag text for a run's depth; a run with none is Standard. */
export function depthLabel(depth: string | null | undefined): string {
  return DEPTH_LABELS[(depth ?? "standard") as Depth] ?? depth ?? "Standard";
}

export function researchOf(info: DepthInfo): ResearchValues {
  const { words: _, ...values } = info.values;
  return values;
}

/** The writer's output limit, as the server computes it. */
export function outputTokens(words: number, cap: number): number {
  return Math.min(Math.max(MIN_OUTPUT_TOKENS, 2 * words), cap);
}

/** The room the profile's window leaves after the reserve and `output`; null when unknown. */
function room(profile: ProfileInfo | undefined, output: (cap: number) => number): number | null {
  const window = profile?.context_window;
  const reserve = profile?.prompt_reserve_tokens;
  const cap = profile?.max_output_tokens;
  if (!window || reserve == null || cap == null) return null;
  return Math.max(0, window - reserve - output(cap));
}

/** The writer's context budget the profile's window leaves; null when the profile has no limits. */
export function effectiveContext(profile: ProfileInfo | undefined, words: number): number | null {
  return room(profile, (cap) => outputTokens(words, cap));
}

/** The gap step's context budget the profile's window leaves; null when unknown. */
export function effectiveGapContext(profile: ProfileInfo | undefined): number | null {
  return room(profile, () => GAP_OUTPUT_TOKENS);
}

/** True when a number is asked and it is above the effective budget. */
export function isClamped(asked: TokenBudget, effective: number | null): asked is number {
  return asked !== "auto" && effective !== null && asked > effective;
}

export const fmtN = (n: number) => n.toLocaleString("en-US");
const fmtK = (n: number) => `${Math.round(n / 1000)}k`;

/**
 * "~<P> pages · <R> rounds · ~<C> LLM calls", plus the context clamp when there is one. Each round
 * after the first searches up to `queries_per_round` follow-ups and costs one gap call.
 */
export function estimate(
  values: ResearchValues,
  effective: number | null,
  rounds: number = values.rounds,
): string {
  const found =
    (values.sub_queries + 1) * values.results_per_query +
    (rounds - 1) * values.queries_per_round * values.results_per_query;
  const pages = Math.min(values.max_pages, found);
  const calls = (values.sub_queries > 0 ? 1 : 0) + (rounds - 1) + 1;
  const line = `~${pages} pages · ${rounds} round${rounds === 1 ? "" : "s"} · ~${calls} LLM calls`;
  const asked = values.context_tokens;
  if (!isClamped(asked, effective)) return line;
  return `${line} · context ${fmtK(asked)} → ${fmtK(effective ?? 0)} (model window)`;
}

export function loadCustom(): Partial<ResearchValues> | null {
  try {
    const saved = localStorage.getItem(CUSTOM_KEY);
    return saved ? (JSON.parse(saved) as Partial<ResearchValues>) : null;
  } catch {
    return null;
  }
}

export function saveCustom(values: ResearchValues): void {
  try {
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(values));
  } catch {
    // Blocked storage: Custom falls back to the previous depth's values next time.
  }
}

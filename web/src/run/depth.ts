// Depth presets in the UI: labels, the effective context budgets, the estimate line, and the
// Custom values remembered in browser storage.
import type { DepthInfo, ResearchValues, TokenBudget } from "../api/types";

/** A preset name from `GET /api/depths` (built in or user), or `custom`. */
export type Depth = string;

/** A model's limits and the profile's prompt reserve, which set the auto budgets. */
export type Limits = {
  context_window: number;
  max_output_tokens: number;
  prompt_reserve_tokens: number | null;
};

const DEPTH_LABELS: Record<string, string> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
  exhaustive: "Exhaustive",
  custom: "Custom",
};

const RESEARCH_FIELDS: (keyof ResearchValues)[] = [
  "sub_queries",
  "results_per_query",
  "max_pages",
  "rounds",
  "queries_per_round",
  "passages_per_query",
];

export const CUSTOM_DESCRIPTION = "Set every value yourself.";
const CUSTOM_KEY = "wosarcher-depth-custom";
const MIN_OUTPUT_TOKENS = 1024;
/** Output tokens the gap step's answer reserves, as the server computes it. */
const GAP_OUTPUT_TOKENS = 768;

/** The label of a depth: built-in presets and Custom are capitalized, user presets as named. */
export function depthLabel(depth: string | null | undefined): string {
  const name = depth ?? "standard";
  return DEPTH_LABELS[name] ?? name;
}

export function researchOf(info: DepthInfo): ResearchValues {
  const { words: _, ...values } = info.values;
  return values;
}

/** The writer's output limit, as the server computes it. */
export function outputTokens(words: number, cap: number): number {
  return Math.min(Math.max(MIN_OUTPUT_TOKENS, 2 * words), cap);
}

/** The room the model's window leaves after the reserve and `output`; null when unknown. */
function room(limits: Limits, output: number): number | null {
  if (limits.prompt_reserve_tokens == null) return null;
  return Math.max(0, limits.context_window - limits.prompt_reserve_tokens - output);
}

/** The writer's context budget the model's window leaves; null when the reserve is unknown. */
export function effectiveContext(limits: Limits, words: number): number | null {
  return room(limits, outputTokens(words, limits.max_output_tokens));
}

/** The gap step's context budget the model's window leaves; null when unknown. */
export function effectiveGapContext(limits: Limits): number | null {
  return room(limits, GAP_OUTPUT_TOKENS);
}

/** True when a number is asked and it is above the window, rounded down to thousands. */
export function isClamped(asked: TokenBudget, limits: Limits): asked is number {
  return asked !== "auto" && asked > windowCap(limits);
}

/** The clamp a budget shows: the model window rounded down to thousands. */
export function windowCap(limits: Limits): number {
  return Math.floor(limits.context_window / 1000) * 1000;
}

export const fmtN = (n: number) => n.toLocaleString("en-US");

/**
 * "~<P> pages · <R> rounds · ~<C> LLM calls". Each round after the first searches up to
 * `queries_per_round` follow-ups and costs one gap call.
 */
export function estimate(values: ResearchValues, rounds: number = values.rounds): string {
  const found =
    (values.sub_queries + 1) * values.results_per_query +
    (rounds - 1) * values.queries_per_round * values.results_per_query;
  const pages = Math.min(values.max_pages, found);
  const calls = (values.sub_queries > 0 ? 1 : 0) + (rounds - 1) + 1;
  return `~${pages} pages · ${rounds} round${rounds === 1 ? "" : "s"} · ~${calls} LLM calls`;
}

export function loadCustom(): Partial<ResearchValues> | null {
  try {
    const saved = localStorage.getItem(CUSTOM_KEY);
    if (!saved) return null;
    const parsed = JSON.parse(saved) as Record<string, unknown>;
    // Only the six research values; anything else saved earlier is dropped.
    return Object.fromEntries(
      RESEARCH_FIELDS.filter((f) => typeof parsed[f] === "number").map((f) => [f, parsed[f]]),
    );
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

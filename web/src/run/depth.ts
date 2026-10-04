// Depth presets in the UI: labels, the effective context budget, the estimate line, and the
// Custom values remembered in browser storage.
import type { DepthInfo, ProfileInfo, ResearchValues } from "../api/types";

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

/** The tag text for a run's depth; a run with none is Standard. */
export function depthLabel(depth: string | null | undefined): string {
  return DEPTH_LABELS[(depth ?? "standard") as Depth] ?? depth ?? "Standard";
}

export function researchOf(info: DepthInfo): ResearchValues {
  const { words: _, queries_per_round: __, ...values } = info.values;
  return values;
}

/** The writer's output limit, as the server computes it. */
export function outputTokens(words: number, cap: number | null | undefined): number {
  const tokens = Math.max(MIN_OUTPUT_TOKENS, 2 * words);
  return cap ? Math.min(tokens, cap) : tokens;
}

/** The context budget the profile's window leaves; null when the profile has no limits. */
export function effectiveContext(profile: ProfileInfo | undefined, words: number): number | null {
  if (!profile?.context_window || profile.prompt_reserve_tokens == null) return null;
  const room =
    profile.context_window -
    profile.prompt_reserve_tokens -
    outputTokens(words, profile.max_output_tokens);
  return Math.max(0, room);
}

export const fmtN = (n: number) => n.toLocaleString("en-US");
const fmtK = (n: number) => `${Math.round(n / 1000)}k`;

/**
 * "~<P> pages · <R> rounds · ~<C> LLM calls", plus the context clamp when there is one. Each round
 * after the first searches up to `queriesPerRound` follow-ups and costs one gap call.
 */
export function estimate(
  values: ResearchValues,
  effective: number | null,
  queriesPerRound: number,
  rounds: number = values.rounds,
): string {
  const found =
    (values.sub_queries + 1) * values.results_per_query +
    (rounds - 1) * queriesPerRound * values.results_per_query;
  const pages = Math.min(values.max_pages, found);
  const calls = (values.sub_queries > 0 ? 1 : 0) + (rounds - 1) + 1;
  const line = `~${pages} pages · ${rounds} round${rounds === 1 ? "" : "s"} · ~${calls} LLM calls`;
  if (effective === null || values.context_tokens <= effective) return line;
  return `${line} · context ${fmtK(values.context_tokens)} → ${fmtK(effective)} (model window)`;
}

export function loadCustom(): ResearchValues | null {
  try {
    const saved = localStorage.getItem(CUSTOM_KEY);
    return saved ? (JSON.parse(saved) as ResearchValues) : null;
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

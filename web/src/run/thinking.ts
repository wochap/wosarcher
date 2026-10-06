// The run's model and thinking levels: the New run values, their browser storage, the request's
// `llm` patch, and the tags the headers show.
import type { Effort, ReasoningOptions, RunCreate } from "../api/types";

export const STEPS = ["plan", "gap", "write"] as const;
export type Step = (typeof STEPS)[number];
export const EFFORTS: Effort[] = ["none", "low", "medium", "high", "default"];
export const STEP_LABELS: Record<Step, string> = { plan: "Plan", gap: "Gap", write: "Write" };
export const EFFORT_LABELS: Record<Effort, string> = {
  none: "None",
  low: "Low",
  medium: "Medium",
  high: "High",
  default: "Default",
};

/** The Model input as typed (empty: the profile's model) and a level per step. */
export type LlmValues = { model: string; reasoning: ReasoningOptions };
export const NO_THINKING: ReasoningOptions = { plan: "none", gap: "none", write: "none" };
export const DEFAULT_LLM: LlmValues = { model: "", reasoning: NO_THINKING };

const LLM_KEY = "wosarcher.llm";

export function loadLlm(): LlmValues {
  try {
    const saved = localStorage.getItem(LLM_KEY);
    if (!saved) return DEFAULT_LLM;
    const parsed = JSON.parse(saved) as Partial<LlmValues>;
    return {
      model: typeof parsed.model === "string" ? parsed.model : "",
      reasoning: { ...NO_THINKING, ...parsed.reasoning },
    };
  } catch {
    return DEFAULT_LLM;
  }
}

export function saveLlm(values: LlmValues): void {
  try {
    localStorage.setItem(LLM_KEY, JSON.stringify(values));
  } catch {
    // Blocked storage: the fields start empty next time.
  }
}

/** The request's `llm`: the model when typed, the steps that differ from none; none when empty. */
export function llmPatch(values: LlmValues): RunCreate["llm"] {
  const model = values.model.trim();
  const reasoning = Object.fromEntries(
    STEPS.filter((s) => values.reasoning[s] !== "none").map((s) => [s, values.reasoning[s]]),
  );
  if (!model && !Object.keys(reasoning).length) return undefined;
  return { ...(model ? { model } : {}), ...(Object.keys(reasoning).length ? { reasoning } : {}) };
}

/** "Write thinking high" per step whose level is not none, in step order. */
export function thinkingTags(reasoning: Partial<ReasoningOptions> | null | undefined): string[] {
  return STEPS.filter((s) => (reasoning?.[s] ?? "none") !== "none").map(
    (s) => `${STEP_LABELS[s]} thinking ${reasoning?.[s]}`,
  );
}

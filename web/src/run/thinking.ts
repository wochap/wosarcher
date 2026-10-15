// Thinking levels per LLM step: their labels and the tags the headers show.
import type { Effort, ReasoningOptions, RunKind } from "../api/types";

export const STEPS = ["plan", "gap", "write", "draft", "extract"] as const;
export type Step = (typeof STEPS)[number];
/** The steps each run kind uses. */
export const KIND_STEPS: Record<RunKind, readonly Step[]> = {
  research: ["plan", "gap", "write"],
  catalog: ["draft", "extract"],
};
export const EFFORTS: Effort[] = ["none", "low", "medium", "high", "default"];
export const STEP_LABELS: Record<Step, string> = {
  plan: "Plan",
  gap: "Gap",
  write: "Write",
  draft: "Draft",
  extract: "Extract",
};
export const EFFORT_LABELS: Record<Effort, string> = {
  none: "None",
  low: "Low",
  medium: "Medium",
  high: "High",
  default: "Default",
};

/** "Write thinking high" per step whose level is not none, in step order. */
export function thinkingTags(reasoning: Partial<ReasoningOptions> | null | undefined): string[] {
  return STEPS.filter((s) => (reasoning?.[s] ?? "none") !== "none").map(
    (s) => `${STEP_LABELS[s]} thinking ${reasoning?.[s]}`,
  );
}

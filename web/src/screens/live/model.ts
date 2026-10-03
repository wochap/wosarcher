// Small derivations the Live run parts share.
import { useEffect, useState } from "react";
import { capitalize } from "../../components/tones";
import { PHASES, type PhaseId, type RunView } from "../../run/reducer";

export const INTERRUPTED = "The run stopped without a final event.";

export const stageLabel = (stage: string) => capitalize(stage);

export const recipeOf = (until: string | null | undefined) =>
  until === "select" ? "context" : "report";

/** What unloads while a stage waits for the device: "scorer", "embeddings model". */
const MODELS: Record<string, string> = {
  plan: "planner LLM",
  prefilter: "embeddings model",
  score: "scorer",
  write: "LLM",
};
export function unloading(waitReason: string | undefined): string {
  const stage = (waitReason ?? "").split(" ")[0];
  return MODELS[stage] ?? `${stage} model`;
}

/** An interrupted run's open phases read as failed, with the interruption as their error. */
export function settled(run: RunView): RunView {
  if (run.status !== "interrupted") return run;
  const phases = { ...run.phases };
  for (const id of PHASES) {
    if (phases[id].state === "running" || phases[id].state === "waiting") {
      phases[id] = { ...phases[id], state: "failed", error: INTERRUPTED };
    }
  }
  return { ...run, phases };
}

/** The stage a failed, interrupted, or cancelled run stopped at. */
export function stoppedAt(run: RunView): PhaseId | undefined {
  if (run.failure?.stage) return run.failure.stage as PhaseId;
  return (
    PHASES.find((id) =>
      ["failed", "cancelled", "running", "waiting"].includes(run.phases[id].state),
    ) ?? PHASES.find((id) => run.phases[id].state === "pending")
  );
}

/** The phases a recipe never runs: everything after `until`. */
export function skippedByRecipe(run: RunView, id: PhaseId): boolean {
  if (!run.until) return false;
  return PHASES.indexOf(id) > PHASES.indexOf(run.until as PhaseId);
}

/** Seconds since the run started, up to its end. */
export function elapsedSeconds(run: RunView, now: number): number {
  if (!run.startedAt) return 0;
  const end = run.endedAt ? Date.parse(run.endedAt) : now;
  return Math.max(0, (end - Date.parse(run.startedAt)) / 1000);
}

/** The current time, ticking every second while `ticking`. */
export function useNow(ticking: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    if (!ticking) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [ticking]);
  return now;
}

// Names the UI uses for the generated contracts. The event union narrows `type`, which the
// schema marks optional because it has a default.
import type * as G from "./generated";

export type Stage = NonNullable<G.RunStarted["stage"]>;
export type WritingOptions = Required<NonNullable<G.RunSummary["writing"]>>;
export type RunStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted";
export type RunSummary = Omit<G.RunSummary, "status" | "writing"> & {
  status: RunStatus;
  writing: WritingOptions;
};
export type RunDetail = Omit<G.RunDetail, "status" | "writing"> & {
  status: RunStatus;
  writing: WritingOptions;
};
export type RunCreate = G.RunCreate;
export type ForkCreate = G.ForkCreate;
export type RunCreated = G.RunCreated;
/** Domain lists: entries are bare domains, matched with their subdomains. */
export type DomainLists = { allow: string[]; block: string[] };
export type ServerSettings = {
  writing: WritingOptions;
  sources: string;
  domains: DomainLists;
  max_concurrent_runs: number;
};
/** Where a run was started: the browser, an API token, or the `wosarcher` CLI. */
export type Origin = G.Origin;
export type SlotHolder = G.SlotHolder;
export type SlotState = Required<G.SlotState>;
export type RunQueuedData = G.RunQueuedData;
export type ProfileInfo = G.ProfileInfo;
export type DepthInfo = G.DepthInfo;
export type ProfileSave = G.ProfileSave;
export type ProfileUpdate = G.ProfileUpdate;
export type DepthSave = G.DepthSave;
export type DepthUpdate = G.DepthUpdate;
/** A depth preset's values as saved: the six research values and Length (null: global default). */
export type DepthSaveValues = G.DepthSaveValues;
/** A token budget: a number, or "auto" for all the room the model window leaves. */
export type TokenBudget = number | "auto";
export type ResearchValues = { [K in keyof G.ResearchPatch]-?: number };
/** Thinking effort of one LLM step. */
export type Effort = NonNullable<G.ReasoningOptions["plan"]>;
export type ReasoningOptions = Required<G.ReasoningOptions>;
/** A provider block, in the order the UI lists them. */
export type Block = G.ProviderEntryInfo["block"];
/** The entry chosen per block; a run's `use` or a profile's. */
export type Use = Partial<Record<Block, string>>;
export type ModelInfo = G.ModelInfo;
export type ProviderEntry = G.ProviderEntryInfo;
export type ProvidersReport = G.ProvidersReport;
export type LlmPatch = G.LLMPatch;
export type SessionInfo = G.SessionInfo & { method: "cookie" | "token" | "none" };
export type TokenInfo = G.TokenInfo;
export type TokenCreated = G.TokenCreated;
export type KeptPassage = G.KeptPassage;
export type SourceView = G.SourceView;
export type SourceChunk = G.SourceChunk;
export type ChunkFate = G.ChunkFate;
export type ChunkQueryFate = G.ChunkQueryFate;

type Ev<T extends string, E> = Omit<E, "type"> & { type: T };
export type RunEvent =
  | Ev<"run.queued", G.RunQueued>
  | Ev<"run.started", G.RunStarted>
  | Ev<"run.done", G.RunDone>
  | Ev<"run.failed", G.RunFailed>
  | Ev<"run.cancelled", G.RunCancelled>
  | Ev<"stage.started", G.StageStarted>
  | Ev<"stage.progress", G.StageProgress>
  | Ev<"stage.done", G.StageDone>
  | Ev<"stage.failed", G.StageFailed>
  | Ev<"resource.waiting", G.ResourceWaiting>
  | Ev<"resource.released", G.ResourceReleased>
  | Ev<"plan.ready", G.PlanReady>
  | Ev<"hit.found", G.HitFound>
  | Ev<"page.fetched", G.PageFetched>
  | Ev<"page.failed", G.PageFailed>
  | Ev<"passages.scored", G.PassagesScored>
  | Ev<"round.done", G.RoundDone>
  | Ev<"gap.ready", G.GapReady>
  | Ev<"research.done", G.ResearchDone>
  | Ev<"report.delta", G.ReportDelta>
  | Ev<"report.snapshot", G.ReportSnapshot>;

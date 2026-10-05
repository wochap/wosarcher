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
export type ServerSettings = { writing: WritingOptions; sources: string; domains: DomainLists };
export type ProfileInfo = G.ProfileInfo;
export type DepthInfo = G.DepthInfo;
/** A token budget: a number, or "auto" for all the room the model window leaves. */
export type TokenBudget = number | "auto";
export type ResearchValues = {
  [K in keyof G.ResearchPatch]-?: K extends "context_tokens" | "gap_context_tokens"
    ? TokenBudget
    : number;
};
export type ProviderCheck = G.ProviderCheck;
export type HealthReport = G.HealthReport;
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

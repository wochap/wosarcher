// Names the UI uses for the generated contracts. The event union narrows `type`, which the
// schema marks optional because it has a default.
import type * as G from "./generated";

export type Stage = NonNullable<G.RunStarted["stage"]>;
export type WritingOptions = Required<NonNullable<G.RunSummary["writing"]>>;
export type RunStatus =
  | "queued"
  | "running"
  | "waiting"
  | "done"
  | "failed"
  | "cancelled"
  | "interrupted";
/** `research` (the default for older runs) or `catalog`. */
export type RunKind = "research" | "catalog";
/** Added by hand until the server's summary carries them: the kind, and a catalog's records. */
type KindFields = {
  kind?: RunKind;
  /** Catalog runs: extracted records so far, or the catalog's count when done; else null. */
  nodes?: number | null;
};
export type RunSummary = Omit<G.RunSummary, "status" | "writing" | "form"> &
  KindFields & {
    status: RunStatus;
    writing: WritingOptions | null;
    form?: RunCreate | null;
  };
export type RunDetail = Omit<G.RunDetail, "status" | "writing" | "form"> &
  KindFields & {
    status: RunStatus;
    writing: WritingOptions | null;
    form?: RunCreate | null;
  };
export type Structure = G.Structure;
export type StructureField = G.StructureField;
export type FieldType = G.StructureField["type"];
export type Seed = G.Seed;
export type Limits = Required<G.Limits>;
export type ExpandBy = NonNullable<G.Structure["expand"]>;
export type CatalogOutput = NonNullable<G.Structure["output"]>;
export type RunCreate = G.RunCreate & { kind?: RunKind; structure?: Structure | null };
export type ForkCreate = G.ForkCreate & { limits?: G.Limits };
/** `POST /api/catalog/draft`: the brief and the profile's choices; attachments go alongside. */
export type DraftRequest = { brief: string; profile?: string; use?: Use; llm?: LlmPatch };
/** One record of `catalog.json`: the structure's fields, `sources`, and `flags`. */
export type CatalogRecord = Record<string, unknown> & {
  sources?: Record<string, string>;
  flags?: string[];
};
/** `catalog.json`. */
export type Catalog = Omit<G.CatalogRecord, "records"> & { records: CatalogRecord[] };
/** One line of `nodes.jsonl`. */
export type CatalogNode = {
  id: string;
  name: string;
  type: string;
  parent_id: string | null;
  depth: number;
  url?: string | null;
  wave?: number;
  status: "discovered" | "expanding" | "extracted" | "failed";
  found_by?: string;
  pages?: string[];
};
export type RunCreated = G.RunCreated;
/** Domain lists: entries are bare domains, matched with their subdomains. */
export type DomainLists = { allow: string[]; block: string[] };
export type QuestionsOptions = Required<G.QuestionsOptions>;
export type QuestionsPatch = G.QuestionsPatch;
export type ServerSettings = {
  writing: WritingOptions;
  sources: string;
  domains: DomainLists;
  max_concurrent_runs: number;
  questions: QuestionsOptions;
};
/** One question of a pause, its option, and an answer to it. */
export type Question = G.Question1;
export type QuestionOption = G.QuestionOption;
export type Answer = G.Answer;
export type ContinueRequest = G.ContinueRequest;
export type PauseKind = G.InputNeededData["kind"];
export type AnsweredBy = G.InputAnsweredData["answered_by"];
export type OpenPause = G.OpenPause;
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
  | Ev<"report.snapshot", G.ReportSnapshot>
  | Ev<"structure.ready", G.StructureReady>
  | Ev<"node.found", G.NodeFound>
  | Ev<"node.extracted", G.NodeExtracted>
  | Ev<"node.failed", G.NodeFailed>
  | Ev<"wave.done", G.WaveDone>
  | Ev<"catalog.done", G.CatalogDone>
  | Ev<"input.needed", G.InputNeeded>
  | Ev<"input.answered", G.InputAnswered>;

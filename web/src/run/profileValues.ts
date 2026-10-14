// The profile's Advanced values on New run: what the profile gives (its `use`, model, and the
// chosen model's values: the profile's `models` over the entry's from `GET /api/providers`), the
// run's edits, and the request they send.
import type {
  Block,
  Effort,
  ModelInfo,
  ProfileInfo,
  ProviderEntry,
  RunCreate,
  TokenBudget,
  Use,
} from "../api/types";
import type { Limits } from "./depth";
import { STEPS } from "./thinking";

export const BLOCKS: Block[] = ["search", "fetch", "prefilter", "score", "llm"];
export const BLOCK_LABELS: Record<Block, string> = {
  search: "Search",
  fetch: "Fetch",
  prefilter: "Prefilter",
  score: "Scorer",
  llm: "LLM",
};
/** The limits the server uses for a model its entry does not list. */
export const FALLBACK_WINDOW = 32768;
export const FALLBACK_OUTPUT = 8192;

/** Every field of the Model and Budgets groups. */
export type ProfileFields = {
  model: string;
  context_window: number;
  max_output_tokens: number;
  plan: Effort;
  gap: Effort;
  write: Effort;
  context_tokens: TokenBudget;
  gap_context_tokens: TokenBudget;
};
export type ProfileField = keyof ProfileFields;
/** The fields edited for this run; an unedited field follows the profile. */
export type ProfileEdits = Partial<ProfileFields>;

/** The fields that carry a source tag instead of "overridden". */
export const MODEL_FIELDS = [
  "model",
  "context_window",
  "max_output_tokens",
  "plan",
  "gap",
  "write",
  "gap_context_tokens",
] as const;
export type ModelField = (typeof MODEL_FIELDS)[number];
/** Where an unedited Model-group value comes from; "" for a built-in default. */
export type ValueSource = "profile" | "entry" | "";

/** The values the profile gives, with the chosen entries and where each model value comes from. */
export type ProfileBase = ProfileFields & {
  use: Record<Block, string>;
  sources: Record<ModelField, ValueSource>;
};

/** The entries of one block, in the order the server lists them. */
export function entriesOf(entries: ProviderEntry[], block: Block): ProviderEntry[] {
  return entries.filter((e) => e.block === block);
}

/** An llm entry's default model: its `model`, or else the first one it lists. */
export function defaultModel(entry: ProviderEntry | undefined): string {
  return entry?.model || entry?.models?.[0]?.id || "";
}

/** The profile's entry per block; a block it does not resolve is empty. */
function profileUse(profile: ProfileInfo | undefined): Record<Block, string> {
  return Object.fromEntries(BLOCKS.map((b) => [b, profile?.use?.[b] ?? ""])) as Record<
    Block,
    string
  >;
}

/**
 * What the profile gives with `use` applied. A switched LLM takes its entry's default model;
 * the limits, thinking, and gap budget are those of `model` (the model shown) on that entry.
 */
export function profileBase(
  profile: ProfileInfo | undefined,
  entries: ProviderEntry[],
  use: Use,
  model?: string,
): ProfileBase {
  const chosen = { ...profileUse(profile), ...use };
  const llm = entries.find((e) => e.block === "llm" && e.name === chosen.llm);
  const own = use.llm ? "" : (profile?.model ?? "");
  const base = own || defaultModel(llm);
  const shown = model ?? base;
  const entry = llm?.models?.find((m) => m.id === shown);
  const tuned = profile?.models?.find((m) => m.id === shown);
  /** The profile's value for the model, else the entry's, with its source. */
  const pick = <T>(of: (m: ModelInfo) => T | null | undefined): [T | undefined, ValueSource] => {
    const mine = tuned ? of(tuned) : undefined;
    if (mine != null) return [mine, "profile"];
    const listed = entry ? of(entry) : undefined;
    return listed != null ? [listed, "entry"] : [undefined, ""];
  };
  const [window, windowFrom] = pick((m) => m.context_window);
  const [output, outputFrom] = pick((m) => m.max_output_tokens);
  const [plan, planFrom] = pick((m) => m.reasoning?.plan);
  const [gap, gapFrom] = pick((m) => m.reasoning?.gap);
  const [write, writeFrom] = pick((m) => m.reasoning?.write);
  const [gapBudget, gapBudgetFrom] = pick((m) => m.gap_context_tokens);
  return {
    use: chosen,
    model: base,
    context_window: window ?? FALLBACK_WINDOW,
    max_output_tokens: output ?? FALLBACK_OUTPUT,
    plan: plan ?? "none",
    gap: gap ?? "none",
    write: write ?? "none",
    context_tokens: profile?.context_tokens ?? "auto",
    gap_context_tokens: gapBudget ?? "auto",
    sources: {
      model: own ? "profile" : base ? "entry" : "",
      context_window: windowFrom,
      max_output_tokens: outputFrom,
      plan: planFrom,
      gap: gapFrom,
      write: writeFrom,
      gap_context_tokens: gapBudgetFrom,
    },
  };
}

/** The tag of a Model-group field: "edited", "from profile", "from entry", or none. */
export function sourceTag(base: ProfileBase, edits: ProfileEdits, field: ModelField): string {
  if (field in edits) return "edited";
  const from = base.sources[field];
  return from ? `from ${from}` : "";
}

/** The limits the auto budgets follow. */
export function limitsOf(values: ProfileFields, profile: ProfileInfo | undefined): Limits {
  return {
    context_window: values.context_window,
    max_output_tokens: values.max_output_tokens,
    prompt_reserve_tokens: profile?.prompt_reserve_tokens ?? null,
  };
}

/** The run's profile choices: changed blocks and edited fields. */
export type ProfileChoice = { use: Use; edits: ProfileEdits };

type Context = { profile: ProfileInfo | undefined; entries: ProviderEntry[] };

/** Drops the blocks and fields equal to what the profile gives, so they stop counting. */
function normalize({ use, edits }: ProfileChoice, { profile, entries }: Context): ProfileChoice {
  const given = profileUse(profile);
  const keptUse = Object.fromEntries(
    Object.entries(use).filter(([b, name]) => given[b as Block] !== name),
  ) as Use;
  const base = profileBase(profile, entries, keptUse, edits.model);
  const keptEdits = Object.fromEntries(
    Object.entries(edits).filter(([f, v]) => String(base[f as ProfileField]) !== String(v)),
  ) as ProfileEdits;
  return { use: keptUse, edits: keptEdits };
}

/** Switching the LLM drops the edits its models own; the Model follows the new entry. */
const MODEL_OWNED: readonly ProfileField[] = MODEL_FIELDS;

export function pickEntry(
  choice: ProfileChoice,
  block: Block,
  name: string,
  context: Context,
): ProfileChoice {
  const edits = { ...choice.edits };
  if (block === "llm") for (const f of MODEL_OWNED) delete edits[f];
  return normalize({ use: { ...choice.use, [block]: name }, edits }, context);
}

/** Edits a field; a new Model drops the window and output edits, which follow the model. */
export function editField<F extends ProfileField>(
  choice: ProfileChoice,
  field: F,
  value: ProfileFields[F],
  context: Context,
): ProfileChoice {
  const edits: ProfileEdits = { ...choice.edits, [field]: value };
  if (field === "model") {
    delete edits.context_window;
    delete edits.max_output_tokens;
  }
  return normalize({ use: choice.use, edits }, context);
}

export function changedCount({ use, edits }: ProfileChoice): number {
  return Object.keys(use).length + Object.keys(edits).length;
}

/** The request's `use` and `llm`: only the changed blocks and the edited fields. */
export function profilePatch({ use, edits }: ProfileChoice): Pick<RunCreate, "use" | "llm"> {
  const patch: Pick<RunCreate, "use" | "llm"> = {};
  if (Object.keys(use).length) patch.use = use as Record<string, string>;
  const { plan, gap, write, model, ...budgets } = edits;
  const levels = { plan, gap, write };
  const reasoning = Object.fromEntries(STEPS.filter((s) => levels[s]).map((s) => [s, levels[s]]));
  const fields = {
    ...(model?.trim() ? { model: model.trim() } : {}),
    ...budgets,
    ...(Object.keys(reasoning).length ? { reasoning } : {}),
  };
  if (Object.keys(fields).length) patch.llm = fields;
  return patch;
}

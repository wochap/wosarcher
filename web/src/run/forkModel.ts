// The Model group of the Rewrite and Re-extract dialogs: the viewed run's values, the edits, the
// refill of unedited values when the entry or model changes, and the fork's `use` and `llm`.
import type {
  Effort,
  ForkCreate,
  ProfileInfo,
  ProviderEntry,
  RunDetail,
  TokenBudget,
} from "../api/types";
import {
  defaultModel,
  entriesOf,
  FALLBACK_OUTPUT,
  FALLBACK_WINDOW,
  type ModelValues,
  modelValues,
  type ProfileEdits,
  profilePatch,
  type ValueSource,
} from "./profileValues";

/** The thinking step the dialog shows. */
export type ForkStep = "write" | "extract";

/** The rows of the group; `llm` is the entry and `effort` the dialog's thinking step. */
export type ForkField =
  | "llm"
  | "model"
  | "context_window"
  | "max_output_tokens"
  | "effort"
  | "context_tokens";
export type ForkValues = {
  llm: string;
  model: string;
  context_window: number;
  max_output_tokens: number;
  effort: Effort;
  context_tokens: TokenBudget;
};

export type ForkModelState = { values: ForkValues; edited: ReadonlySet<ForkField> };
/** What the dialog needs besides the state: the parent's profile, the llm entries, the step. */
export type ForkContext = {
  profile: ProfileInfo | undefined;
  entries: ProviderEntry[];
  step: ForkStep;
};

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => (v && typeof v === "object" ? (v as Obj) : {});

/** The viewed run's values, from `use.llm` and the settings it ran with. */
export function forkModelBase(detail: RunDetail, step: ForkStep): ForkValues {
  const settings = obj(detail.request?.settings);
  const llm = obj(settings.llm);
  const num = (v: unknown, fallback: number) => (typeof v === "number" ? v : fallback);
  const budget = obj(settings.select).max_context_tokens;
  const effort = obj(llm.reasoning)[step];
  return {
    llm: (detail.request?.use as Record<string, string> | undefined)?.llm ?? detail.use?.llm ?? "",
    model: typeof llm.model === "string" ? llm.model : (detail.model ?? ""),
    context_window: num(llm.context_window, FALLBACK_WINDOW),
    max_output_tokens: num(llm.max_output_tokens, FALLBACK_OUTPUT),
    effort: (typeof effort === "string" ? effort : "none") as Effort,
    context_tokens: typeof budget === "number" ? budget : "auto",
  };
}

export function initialState(base: ForkValues): ForkModelState {
  return { values: base, edited: new Set() };
}

/** The shown model's values on the shown entry, with their sources. */
export function shownValues(state: ForkModelState, { profile, entries }: ForkContext): ModelValues {
  const entry = entriesOf(entries, "llm").find((e) => e.name === state.values.llm);
  return modelValues(profile, entry, state.values.model);
}

/** Where a row's value comes from: "edited", "from profile", "from entry", or none. */
export function sourceOf(state: ForkModelState, field: ForkField, context: ForkContext): string {
  if (state.edited.has(field)) return "edited";
  if (field === "llm" || field === "model" || field === "context_tokens") return "";
  const key = field === "effort" ? context.step : field;
  const from: ValueSource = shownValues(state, context).sources[key];
  return from ? `from ${from}` : "";
}

/** Refills every unedited model value from the shown entry and model. */
function refill(state: ForkModelState, context: ForkContext): ForkModelState {
  const { values } = shownValues(state, context);
  const next = { ...state.values };
  if (!state.edited.has("context_window")) next.context_window = values.context_window;
  if (!state.edited.has("max_output_tokens")) next.max_output_tokens = values.max_output_tokens;
  if (!state.edited.has("effort")) next.effort = values[context.step];
  return { values: next, edited: state.edited };
}

function withEdit(state: ForkModelState, field: ForkField, on: boolean): ReadonlySet<ForkField> {
  const edited = new Set(state.edited);
  if (on) edited.add(field);
  else edited.delete(field);
  return edited;
}

/** Edits a row; a value equal to the base stops counting as edited. A new model refills. */
export function edit<F extends Exclude<ForkField, "llm">>(
  state: ForkModelState,
  base: ForkValues,
  context: ForkContext,
  field: F,
  value: ForkValues[F],
): ForkModelState {
  const next = {
    values: { ...state.values, [field]: value },
    edited: withEdit(state, field, String(value) !== String(base[field])),
  };
  return field === "model" ? refill(next, context) : next;
}

/** Picks an entry: Model takes its default model and the unedited values are refilled. */
export function pickEntry(
  state: ForkModelState,
  context: ForkContext,
  name: string,
): ForkModelState {
  const entry = entriesOf(context.entries, "llm").find((e) => e.name === name);
  const next = {
    values: { ...state.values, llm: name, model: defaultModel(entry) },
    edited: withEdit(state, "model", false),
  };
  return refill(next, context);
}

/** Restores a row's base value (for the entry, the base entry and model) and refills. */
export function reset(
  state: ForkModelState,
  base: ForkValues,
  context: ForkContext,
  field: ForkField,
): ForkModelState {
  if (field === "llm") {
    const next = {
      values: { ...state.values, llm: base.llm, model: base.model },
      edited: withEdit(state, "model", false),
    };
    return refill(next, context);
  }
  const next = {
    values: { ...state.values, [field]: base[field] },
    edited: withEdit(state, field, false),
  };
  return field === "model" ? refill(next, context) : next;
}

/** Whether a row differs from the viewed run's value. */
export function isChanged(state: ForkModelState, base: ForkValues, field: ForkField): boolean {
  return String(state.values[field]) !== String(base[field]);
}

const FIELDS: ForkField[] = [
  "llm",
  "model",
  "context_window",
  "max_output_tokens",
  "effort",
  "context_tokens",
];

/** The rows that differ from the viewed run, for the "· N changed" hint. */
export function changedCount(
  state: ForkModelState,
  base: ForkValues,
  withContextTokens = true,
): number {
  return FIELDS.filter((f) => withContextTokens || f !== "context_tokens").filter((f) =>
    isChanged(state, base, f),
  ).length;
}

/**
 * The fork's `use` and `llm`: the entry when it changed, the model when edited (a picked entry's
 * default model is the server's choice), and the edited rows that
 * differ from the base. Refilled values are left out; the server applies the model's values.
 */
export function forkModelPatch(
  state: ForkModelState,
  base: ForkValues,
  step: ForkStep,
): Pick<ForkCreate, "use" | "llm"> {
  const edits: ProfileEdits = {};
  if (state.edited.has("model") && isChanged(state, base, "model"))
    edits.model = state.values.model;
  for (const f of ["context_window", "max_output_tokens", "context_tokens"] as const) {
    if (state.edited.has(f) && isChanged(state, base, f))
      Object.assign(edits, { [f]: state.values[f] });
  }
  if (state.edited.has("effort") && isChanged(state, base, "effort")) {
    edits[step] = state.values.effort;
  }
  const patch = profilePatch(
    { use: state.values.llm !== base.llm ? { llm: state.values.llm } : {}, edits },
    [step],
  );
  return patch;
}

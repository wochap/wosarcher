// The "Model" group of the Rewrite and Re-extract dialogs: entry, model, limits, the step's
// thinking, and (Rewrite) Context tokens, each marked against the viewed run. The rules live in
// `run/forkModel.ts`; this renders them.
import { ArrowCounterClockwise, Info } from "@phosphor-icons/react";
import { type ReactNode, useEffect, useState } from "react";
import type { ProfileInfo, ProviderEntry, RunDetail } from "../api/types";
import { useApi } from "../app/context";
import { effectiveContext, fmtN, isClamped, windowCap } from "../run/depth";
import {
  edit,
  type ForkContext,
  type ForkField,
  type ForkModelState,
  type ForkStep,
  type ForkValues,
  isChanged,
  pickEntry,
  reset,
  shownValues,
  sourceOf,
} from "../run/forkModel";
import { entriesOf } from "../run/profileValues";
import { EFFORT_LABELS, EFFORTS, STEP_LABELS } from "../run/thinking";
import css from "./ForkModelGroup.module.css";
import { HelpTip } from "./HelpTip";

const FALLBACK_NOTE = "Fallback: no limits set for this model.";
const MAX_TOKENS = 4194304;

type Props = {
  run: RunDetail;
  step: ForkStep;
  /** Rewrite only: the Context tokens row. */
  withContextTokens?: boolean;
  /** The dialog's length, which sets the writer's output allowance. */
  words?: number;
  base: ForkValues;
  value: ForkModelState;
  onChange: (state: ForkModelState) => void;
};

export function ForkModelGroup({
  run,
  step,
  withContextTokens = false,
  words = 0,
  base,
  value,
  onChange,
}: Props) {
  const api = useApi();
  const [entries, setEntries] = useState<ProviderEntry[]>([]);
  const [profile, setProfile] = useState<ProfileInfo>();
  const [models, setModels] = useState<string[]>([]);
  const { llm, model } = value.values;

  useEffect(() => {
    let live = true;
    api.listProviders().then(
      (r) => live && setEntries(r.entries),
      () => {},
    );
    api.listProfiles().then(
      (list) => live && setProfile(list.find((p) => p.name === run.profile)),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [api, run.profile]);
  useEffect(() => {
    let live = true;
    api.listModels(llm).then(
      (ids) => live && setModels(ids),
      () => live && setModels([]),
    );
    return () => {
      live = false;
    };
  }, [api, llm]);

  const context: ForkContext = { profile, entries, step };
  const shown = shownValues(value, context);
  const llms = entriesOf(entries, "llm");
  const names =
    llms.some((e) => e.name === llm) || !llm ? llms : [{ name: llm } as ProviderEntry, ...llms];
  const label = `${STEP_LABELS[step]} thinking`;
  const reserve = Number(
    (run.request?.settings as { select?: { prompt_reserve_tokens?: unknown } } | undefined)?.select
      ?.prompt_reserve_tokens,
  );
  const limits = {
    context_window: value.values.context_window,
    max_output_tokens: value.values.max_output_tokens,
    prompt_reserve_tokens: Number.isFinite(reserve)
      ? reserve
      : (profile?.prompt_reserve_tokens ?? null),
  };
  const asked = value.values.context_tokens;
  let budgetNote = "";
  if (asked === "auto") {
    const budget = effectiveContext(limits, words);
    budgetNote = budget === null ? "Auto" : `Auto · ${fmtN(budget)}`;
  } else if (isClamped(asked, limits)) {
    budgetNote = `${fmtN(asked)} → ${fmtN(windowCap(limits))} (model window)`;
  }
  const fallback =
    !value.edited.has("context_window") &&
    !value.edited.has("max_output_tokens") &&
    !shown.sources.context_window &&
    !shown.sources.max_output_tokens;

  const set = <F extends Exclude<ForkField, "llm">>(field: F, v: ForkValues[F]) =>
    onChange(edit(value, base, context, field, v));
  const wasText = (field: ForkField): string => {
    const v = base[field];
    if (field === "effort") return EFFORT_LABELS[base.effort];
    return v === "auto" ? "Auto" : String(v);
  };
  const row = (
    field: ForkField,
    title: string,
    help: string,
    id: string,
    control: ReactNode,
    note = "",
  ) => (
    <Row
      key={field}
      id={id}
      label={title}
      help={help}
      source={sourceOf(value, field, context)}
      was={isChanged(value, base, field) ? wasText(field) : ""}
      onReset={() => onChange(reset(value, base, context, field))}
      note={note}
    >
      {control}
    </Row>
  );
  const preset = (field: ForkField) => !isChanged(value, base, field);

  return (
    <fieldset className={css.group}>
      <div className={css.grid}>
        {row(
          "llm",
          "LLM entry",
          "p-llm",
          "fm-llm",
          <select
            id="fm-llm"
            className={`input ${css.input}`}
            data-preset={preset("llm")}
            value={llm}
            onChange={(e) => onChange(pickEntry(value, context, e.target.value))}
          >
            {names.map((e) => (
              <option key={e.name} value={e.name}>
                {e.name}
              </option>
            ))}
          </select>,
        )}
        {row(
          "model",
          "Model",
          "p-model",
          "fm-model",
          <>
            <input
              id="fm-model"
              className={`input ${css.input} ${css.mono}`}
              data-preset={preset("model")}
              list="fm-model-list"
              autoComplete="off"
              spellCheck={false}
              value={model}
              onChange={(e) => set("model", e.target.value)}
            />
            <datalist id="fm-model-list">
              {models.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </>,
        )}
        {(
          [
            ["context_window", "Context window", 1024],
            ["max_output_tokens", "Max output", 256],
          ] as const
        ).map(([field, title, min]) =>
          row(
            field,
            title,
            "p-limits",
            `fm-${field}`,
            <input
              id={`fm-${field}`}
              className={`input ${css.input}`}
              data-preset={preset(field)}
              type="number"
              min={min}
              max={MAX_TOKENS}
              step={1024}
              value={value.values[field]}
              onChange={(e) => set(field, Number(e.target.value) || min)}
            />,
            fallback ? FALLBACK_NOTE : "",
          ),
        )}
        {row(
          "effort",
          label,
          step === "extract" ? "p-think-extract" : "p-think",
          "fm-effort",
          <select
            id="fm-effort"
            className={`input ${css.input}`}
            data-preset={preset("effort")}
            value={value.values.effort}
            onChange={(e) => set("effort", e.target.value as ForkValues["effort"])}
          >
            {EFFORTS.map((level) => (
              <option key={level} value={level}>
                {EFFORT_LABELS[level]}
              </option>
            ))}
          </select>,
        )}
        {withContextTokens &&
          row(
            "context_tokens",
            "Context tokens",
            "p-ctx",
            "fm-context_tokens",
            <input
              id="fm-context_tokens"
              className={`input ${css.input}`}
              data-preset={preset("context_tokens")}
              type="number"
              min={1000}
              step={1000}
              placeholder="Auto"
              value={asked === "auto" ? "" : asked}
              onChange={(e) =>
                set("context_tokens", e.target.value === "" ? "auto" : Number(e.target.value))
              }
            />,
            budgetNote,
          )}
      </div>
    </fieldset>
  );
}

type RowProps = {
  id: string;
  label: string;
  help: string;
  source: string;
  was: string;
  onReset: () => void;
  note: string;
  children: ReactNode;
};

function Row({ id, label, help, source, was, onReset, note, children }: RowProps) {
  return (
    <div className={css.field}>
      <div className={css.label}>
        <label htmlFor={id}>{label}</label>
        <HelpTip help={help} label={label} />
        {source && (
          <span className={css.sourceTag} data-edited={source === "edited"}>
            {source}
          </span>
        )}
      </div>
      {children}
      {was && (
        <span className={css.was}>
          was {was}
          <button
            type="button"
            className={`btn btn-ghost ${css.reset}`}
            aria-label={`Reset ${label}`}
            onClick={onReset}
          >
            <ArrowCounterClockwise aria-hidden="true" />
            Reset
          </button>
        </span>
      )}
      {note && (
        <span className={css.note}>
          <Info aria-hidden="true" />
          {note}
        </span>
      )}
    </div>
  );
}

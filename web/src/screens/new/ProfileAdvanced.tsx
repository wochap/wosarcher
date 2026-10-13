// The profile's Advanced values on New run: the entry per block, the model with its limits and
// thinking, and the context budgets. Edits apply to this run only and are marked "overridden".
import {
  ArrowCounterClockwise,
  CaretDown,
  CaretRight,
  Info,
  LockSimple,
} from "@phosphor-icons/react";
import { type ReactNode, useState } from "react";
import type { Block, Effort, ProfileInfo, ProviderEntry, TokenBudget } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
import { Tag } from "../../components/Tag";
import { effectiveContext, effectiveGapContext, fmtN, isClamped, windowCap } from "../../run/depth";
import {
  BLOCK_LABELS,
  BLOCKS,
  changedCount,
  editField,
  entriesOf,
  limitsOf,
  type ProfileChoice,
  type ProfileField,
  type ProfileFields,
  pickEntry,
  profileBase,
} from "../../run/profileValues";
import { EFFORT_LABELS, EFFORTS, STEP_LABELS, STEPS } from "../../run/thinking";
import css from "./OptionsPanel.module.css";

const BLOCK_HELP: Record<Block, string> = {
  search: "p-search",
  fetch: "p-fetch",
  prefilter: "p-prefilter",
  score: "p-scorer",
  llm: "p-llm",
};
const ROUNDS_LOCK = "Used between rounds; needs 2+ rounds.";
const FALLBACK_NOTE = "Fallback: no limits set for this model.";
const MAX_TOKENS = 4194304;

type Props = {
  profile: ProfileInfo | undefined;
  /** Every entry from `GET /api/providers`. */
  entries: ProviderEntry[];
  choice: ProfileChoice;
  /** IDs the chosen llm entry's endpoint lists, offered as suggestions. */
  models: string[];
  /** The writing Length, which sets the writer's output limit. */
  words: number;
  /** The depth's rounds; gap fields are used only between rounds. */
  rounds: number;
  onChange: (choice: ProfileChoice) => void;
};

export function ProfileAdvanced({
  profile,
  entries,
  choice,
  models,
  words,
  rounds,
  onChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const name = profile?.name ?? "";
  const context = { profile, entries };
  const base = profileBase(profile, entries, choice.use, choice.edits.model);
  const values: ProfileFields = { ...base, ...choice.edits };
  const limits = limitsOf(values, profile);
  const changed = changedCount(choice);
  const lockGap = rounds < 2;
  const Caret = open ? CaretDown : CaretRight;
  const edit = <F extends ProfileField>(field: F, value: ProfileFields[F]) =>
    onChange(editField(choice, field, value, context));

  /** "Auto · <budget>", or the clamp when a number above the window is asked. */
  const budgetNote = (asked: TokenBudget, budget: number | null): string => {
    if (asked === "auto") return budget === null ? "Auto" : `Auto · ${fmtN(budget)}`;
    if (isClamped(asked, limits))
      return `${fmtN(asked)} → ${fmtN(windowCap(limits))} (model window)`;
    return "";
  };
  const budget = (field: "context_tokens" | "gap_context_tokens", typed: string) =>
    edit(field, typed === "" ? "auto" : Number(typed));

  return (
    <>
      <button
        type="button"
        className={`btn btn-ghost ${css.advanced}`}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Caret aria-hidden="true" />
        Advanced
        <span className={css.advHint}>{changed ? `· ${changed} changed` : `· ${name} values`}</span>
      </button>
      {open && (
        <div className={`${css.advBody} ${css.profileBody}`}>
          <div className={css.profileNote}>
            <span className={css.advNote}>
              {changed
                ? `Changed for this run only; the ${name} profile itself is unchanged.`
                : `Values from the ${name} profile. Edits apply to this run only.`}
            </span>
            {changed > 0 && (
              <button
                type="button"
                className={`btn btn-ghost ${css.advanced}`}
                onClick={() => onChange({ use: {}, edits: {} })}
              >
                <ArrowCounterClockwise aria-hidden="true" />
                Reset to profile
              </button>
            )}
          </div>
          <FieldGroup title="Providers">
            {BLOCKS.map((block) => {
              const list = entriesOf(entries, block);
              const one = list.length === 1;
              return (
                <Field
                  key={block}
                  id={`pa-${block}`}
                  label={BLOCK_LABELS[block]}
                  help={BLOCK_HELP[block]}
                  over={block in choice.use}
                  note={one ? "Only one configured." : ""}
                  locked
                >
                  <select
                    id={`pa-${block}`}
                    className={`input ${css.advInput}`}
                    data-preset={!(block in choice.use)}
                    value={base.use[block]}
                    disabled={one}
                    onChange={(e) => onChange(pickEntry(choice, block, e.target.value, context))}
                  >
                    {list.map((e) => (
                      <option key={e.name} value={e.name}>
                        {e.name}
                      </option>
                    ))}
                  </select>
                </Field>
              );
            })}
          </FieldGroup>
          <FieldGroup title="Model">
            <Field id="pa-model" label="Model" help="p-model" over={"model" in choice.edits}>
              <input
                id="pa-model"
                className={`input ${css.advInput} ${css.mono}`}
                data-preset={!("model" in choice.edits)}
                list="pa-model-list"
                autoComplete="off"
                spellCheck={false}
                value={values.model}
                onChange={(e) => edit("model", e.target.value)}
              />
              <datalist id="pa-model-list">
                {models.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </Field>
            {(
              [
                ["context_window", "Context window", 1024],
                ["max_output_tokens", "Max output", 256],
              ] as const
            ).map(([field, label, min]) => (
              <Field
                key={field}
                id={`pa-${field}`}
                label={label}
                help="p-limits"
                over={field in choice.edits}
                note={field in choice.edits || base.listed[field] ? "" : FALLBACK_NOTE}
              >
                <input
                  id={`pa-${field}`}
                  className={`input ${css.advInput}`}
                  data-preset={!(field in choice.edits)}
                  type="number"
                  min={min}
                  max={MAX_TOKENS}
                  step={1024}
                  value={values[field]}
                  onChange={(e) => edit(field, Number(e.target.value) || min)}
                />
              </Field>
            ))}
            {STEPS.map((step) => {
              const locked = step === "gap" && lockGap;
              const label = `${STEP_LABELS[step]} thinking`;
              return (
                <Field
                  key={step}
                  id={`pa-${step}`}
                  label={label}
                  help="p-think"
                  over={step in choice.edits}
                  note={locked ? ROUNDS_LOCK : ""}
                  locked
                >
                  <select
                    id={`pa-${step}`}
                    className={`input ${css.advInput}`}
                    data-preset={!(step in choice.edits)}
                    value={values[step]}
                    disabled={locked}
                    onChange={(e) => edit(step, e.target.value as Effort)}
                  >
                    {EFFORTS.map((level) => (
                      <option key={level} value={level}>
                        {EFFORT_LABELS[level]}
                      </option>
                    ))}
                  </select>
                </Field>
              );
            })}
          </FieldGroup>
          <FieldGroup title="Budgets">
            <Field
              id="pa-context_tokens"
              label="Context tokens"
              help="p-ctx"
              over={"context_tokens" in choice.edits}
              note={budgetNote(values.context_tokens, effectiveContext(limits, words))}
            >
              <BudgetInput
                id="pa-context_tokens"
                value={values.context_tokens}
                edited={"context_tokens" in choice.edits}
                onChange={(typed) => budget("context_tokens", typed)}
              />
            </Field>
            <Field
              id="pa-gap_context_tokens"
              label="Gap context tokens"
              help="p-gapctx"
              over={"gap_context_tokens" in choice.edits}
              note={
                lockGap
                  ? ROUNDS_LOCK
                  : budgetNote(values.gap_context_tokens, effectiveGapContext(limits))
              }
              locked={lockGap}
            >
              <BudgetInput
                id="pa-gap_context_tokens"
                value={values.gap_context_tokens}
                edited={"gap_context_tokens" in choice.edits}
                disabled={lockGap}
                onChange={(typed) => budget("gap_context_tokens", typed)}
              />
            </Field>
          </FieldGroup>
        </div>
      )}
    </>
  );
}

function FieldGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className={css.fieldGroup}>
      <legend className={css.fieldGroupTitle}>{title}</legend>
      <div className={css.advGrid}>{children}</div>
    </fieldset>
  );
}

type FieldProps = {
  id: string;
  label: string;
  help: string;
  over: boolean;
  /** The note under the control; `locked` shows it with the lock icon. */
  note?: string;
  locked?: boolean;
  children: ReactNode;
};

function Field({ id, label, help, over, note, locked, children }: FieldProps) {
  const NoteIcon = locked ? LockSimple : Info;
  return (
    <div className={css.advField}>
      <div className={`${css.advLabel} ${css.advLabelWrap}`}>
        <label htmlFor={id}>{label}</label>
        <HelpTip help={help} label={label} />
        {over && (
          <span className={css.overMark}>
            <Tag variant="outline" small>
              overridden
            </Tag>
            <HelpTip help="p-over" />
          </span>
        )}
      </div>
      {children}
      {note && (
        <span className={css.advFieldNote}>
          <NoteIcon aria-hidden="true" />
          {note}
        </span>
      )}
    </div>
  );
}

type BudgetProps = {
  id: string;
  value: TokenBudget;
  edited: boolean;
  disabled?: boolean;
  onChange: (typed: string) => void;
};

/** A budget input: empty means Auto. */
function BudgetInput({ id, value, edited, disabled, onChange }: BudgetProps) {
  return (
    <input
      id={id}
      className={`input ${css.advInput}`}
      data-preset={!edited}
      type="number"
      min={1000}
      step={1000}
      placeholder="Auto"
      value={value === "auto" ? "" : value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

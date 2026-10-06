// The Depth row of the Options panel: the preset control, its description and estimate, and the
// Advanced values. Editing a value switches to Custom.
import { CaretDown, CaretRight, Info, LockSimple } from "@phosphor-icons/react";
import { type ReactNode, useState } from "react";
import type { ResearchValues, TokenBudget } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
import { Seg } from "../../components/Seg";
import { DEPTH_LABELS, type Depth, estimate, fmtN, isClamped } from "../../run/depth";
import css from "./OptionsPanel.module.css";

type Field = keyof ResearchValues;

const FIELDS: [Field, string, number, number, number][] = [
  ["sub_queries", "Sub-queries", 1, 12, 1],
  ["results_per_query", "Results per query", 1, 20, 1],
  ["max_pages", "Max pages", 5, 300, 5],
  ["rounds", "Rounds", 1, 8, 1],
  ["queries_per_round", "Follow-ups per round", 1, 12, 1],
  ["passages_per_query", "Passages per query", 1, 40, 1],
  ["context_tokens", "Context tokens", 1000, 128000, 1000],
  ["gap_context_tokens", "Gap context tokens", 1000, 128000, 1000],
];
/** Fields that accept "auto"; emptying the input selects it. */
const BUDGETS: Partial<Record<Field, true>> = { context_tokens: true, gap_context_tokens: true };
const HELP: Record<Field, string> = {
  sub_queries: "d-subq",
  results_per_query: "d-rpq",
  max_pages: "d-pages",
  rounds: "d-rounds",
  queries_per_round: "d-qpr",
  passages_per_query: "d-ppq",
  context_tokens: "d-ctx",
  gap_context_tokens: "d-gap-ctx",
};

type Props = {
  depth: Depth;
  depths: Depth[];
  description: string;
  values: ResearchValues;
  /** The context budget the profile's window leaves; null when unknown. */
  effective: number | null;
  /** The gap step's context budget the profile's window leaves; null when unknown. */
  gapEffective: number | null;
  /** Files-only runs use one round. */
  filesOnly: boolean;
  onPick: (depth: Depth) => void;
  onEdit: (field: keyof ResearchValues, value: TokenBudget) => void;
  /** Shown below the research values, inside Advanced. */
  children?: ReactNode;
};

export function DepthGroup({
  depth,
  depths,
  description,
  values,
  effective,
  gapEffective,
  filesOnly,
  onPick,
  onEdit,
  children,
}: Props) {
  const [open, setOpen] = useState(depth === "custom");
  const preset = depth !== "custom";
  const Caret = open ? CaretDown : CaretRight;
  const rounds = filesOnly ? 1 : values.rounds;
  const budgets: Partial<Record<Field, number | null>> = {
    context_tokens: effective,
    gap_context_tokens: gapEffective,
  };
  /** The note under a field: the lock reason, the Auto budget, or the clamp. */
  const noteOf = (field: Field): [string, boolean] => {
    if (field === "rounds" && filesOnly) return ["Files-only runs use 1 round.", true];
    if ((field === "gap_context_tokens" || field === "queries_per_round") && rounds === 1)
      return ["Used between rounds; needs 2+ rounds.", true];
    if (!BUDGETS[field]) return ["", false];
    const asked = values[field];
    const budget = budgets[field] ?? null;
    if (asked === "auto") return [budget === null ? "Auto" : `Auto · ${fmtN(budget)}`, false];
    if (isClamped(asked, budget))
      return [`${fmtN(asked)} → ${fmtN(budget ?? 0)} (model window)`, false];
    return ["", false];
  };
  return (
    <div className={css.row}>
      <div className={css.rowLabel}>
        <span id="depth-l">Depth</span>
        <HelpTip help="depth" />
      </div>
      <div className={`${css.rowControl} ${css.depth}`}>
        <Seg
          label="Depth"
          name="opt-depth"
          value={depth}
          options={depths.map((d) => ({ value: d, label: DEPTH_LABELS[d] }))}
          onChange={(d) => {
            if (d === "custom") setOpen(true);
            onPick(d);
          }}
        />
        <div className={css.depthText}>
          <span className={css.depthDesc}>{description}</span>
          <span aria-live="polite" className={css.estimate}>
            {estimate(values, effective, rounds)}
          </span>
        </div>
        <button
          type="button"
          className={`btn btn-ghost ${css.advanced}`}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <Caret aria-hidden="true" />
          Advanced
          <span className={css.advHint}>
            {preset ? `· ${DEPTH_LABELS[depth]} values` : "· your values"}
          </span>
        </button>
        {open && (
          <div className={css.advBody}>
            <span className={css.advNote}>
              {preset
                ? `${DEPTH_LABELS[depth]} preset. Edit any value to switch to Custom.`
                : "Your Custom values, saved in this browser."}
            </span>
            <div className={css.advGrid}>
              {FIELDS.map(([field, label, min, max, step]) => {
                const [note, locked] = noteOf(field);
                const auto = BUDGETS[field] === true;
                const value = values[field];
                const NoteIcon = locked ? LockSimple : Info;
                return (
                  <div key={field} className={css.advField}>
                    <div className={css.advLabel}>
                      <label htmlFor={`d-${field}`}>{label}</label>
                      <HelpTip help={HELP[field]} />
                    </div>
                    <input
                      id={`d-${field}`}
                      className={`input ${css.advInput}`}
                      data-preset={preset}
                      type="number"
                      min={min}
                      max={max}
                      step={step}
                      placeholder={auto ? "Auto" : undefined}
                      value={field === "rounds" && locked ? 1 : value === "auto" ? "" : value}
                      disabled={locked}
                      onChange={(e) => {
                        if (locked) return;
                        const typed = e.target.value;
                        onEdit(field, auto && typed === "" ? "auto" : Number(typed) || min);
                      }}
                    />
                    {note && (
                      <span className={css.advFieldNote}>
                        <NoteIcon aria-hidden="true" />
                        {note}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

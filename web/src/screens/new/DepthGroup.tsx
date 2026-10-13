// The Depth row of the Options panel: the preset control, its description and estimate, and the
// Advanced values. Editing a value switches to Custom.
import { CaretDown, CaretRight, LockSimple } from "@phosphor-icons/react";
import { useState } from "react";
import type { ResearchValues } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
import { Seg } from "../../components/Seg";
import { type Depth, depthLabel, estimate } from "../../run/depth";
import css from "./OptionsPanel.module.css";

type Field = keyof ResearchValues;

const FIELDS: [Field, string, number, number, number][] = [
  ["sub_queries", "Sub-queries", 1, 12, 1],
  ["results_per_query", "Results per query", 1, 20, 1],
  ["max_pages", "Max pages", 5, 300, 5],
  ["rounds", "Rounds", 1, 8, 1],
  ["queries_per_round", "Follow-ups per round", 1, 12, 1],
  ["passages_per_query", "Passages per query", 1, 40, 1],
];
const HELP: Record<Field, string> = {
  sub_queries: "d-subq",
  results_per_query: "d-rpq",
  max_pages: "d-pages",
  rounds: "d-rounds",
  queries_per_round: "d-qpr",
  passages_per_query: "d-ppq",
};

type Props = {
  depth: Depth;
  depths: Depth[];
  description: string;
  values: ResearchValues;
  /** Files-only runs use one round. */
  filesOnly: boolean;
  onPick: (depth: Depth) => void;
  onEdit: (field: keyof ResearchValues, value: number) => void;
};

export function DepthGroup({
  depth,
  depths,
  description,
  values,
  filesOnly,
  onPick,
  onEdit,
}: Props) {
  const [open, setOpen] = useState(depth === "custom");
  const preset = depth !== "custom";
  const Caret = open ? CaretDown : CaretRight;
  const rounds = filesOnly ? 1 : values.rounds;
  const label = depthLabel(depth);
  /** The lock reason under a field, if any. */
  const lockOf = (field: Field): string => {
    if (field === "rounds" && filesOnly) return "Files-only runs use 1 round.";
    if (field === "queries_per_round" && rounds === 1)
      return "Used between rounds; needs 2+ rounds.";
    return "";
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
          className={css.depthSeg}
          options={depths.map((d) => ({ value: d, label: depthLabel(d) }))}
          onChange={(d) => {
            if (d === "custom") setOpen(true);
            onPick(d);
          }}
        />
        <div className={css.depthText}>
          <span className={css.depthDesc}>{description}</span>
          <span aria-live="polite" className={css.estimate}>
            {estimate(values, rounds)}
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
          <span className={css.advHint}>{preset ? `· ${label} values` : "· your values"}</span>
        </button>
        {open && (
          <div className={css.advBody}>
            <span className={css.advNote}>
              {preset
                ? `${label} preset. Edit any value to switch to Custom.`
                : "Your Custom values, saved in this browser."}
            </span>
            <div className={css.advGrid}>
              {FIELDS.map(([field, label, min, max, step]) => {
                const note = lockOf(field);
                const locked = note !== "";
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
                      value={field === "rounds" && locked ? 1 : values[field]}
                      disabled={locked}
                      onChange={(e) => {
                        if (!locked) onEdit(field, Number(e.target.value) || min);
                      }}
                    />
                    {note && (
                      <span className={css.advFieldNote}>
                        <LockSimple aria-hidden="true" />
                        {note}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

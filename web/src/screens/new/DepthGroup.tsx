// The Depth row of the Options panel: the preset control, its description and estimate, and the
// Advanced values. Editing a value switches to Custom.
import { CaretDown, CaretRight, Info, LockSimple } from "@phosphor-icons/react";
import { useState } from "react";
import type { ResearchValues } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
import { Seg } from "../../components/Seg";
import { DEPTH_LABELS, type Depth, estimate, fmtN } from "../../run/depth";
import css from "./OptionsPanel.module.css";

type Field = keyof ResearchValues | "rounds";

const FIELDS: [Field, string, number, number, number][] = [
  ["sub_queries", "Sub-queries", 1, 12, 1],
  ["results_per_query", "Results per query", 1, 20, 1],
  ["max_pages", "Max pages", 5, 300, 5],
  ["rounds", "Rounds", 1, 8, 1],
  ["passages_per_query", "Passages per query", 1, 40, 1],
  ["context_tokens", "Context tokens", 1000, 128000, 1000],
];
const HELP: Record<Field, string> = {
  sub_queries: "d-subq",
  results_per_query: "d-rpq",
  max_pages: "d-pages",
  rounds: "d-rounds",
  passages_per_query: "d-ppq",
  context_tokens: "d-ctx",
};

type Props = {
  depth: Depth;
  depths: Depth[];
  description: string;
  values: ResearchValues;
  /** The context budget the profile's window leaves; null when unknown. */
  effective: number | null;
  onPick: (depth: Depth) => void;
  onEdit: (field: keyof ResearchValues, value: number) => void;
};

export function DepthGroup({
  depth,
  depths,
  description,
  values,
  effective,
  onPick,
  onEdit,
}: Props) {
  const [open, setOpen] = useState(depth === "custom");
  const preset = depth !== "custom";
  const Caret = open ? CaretDown : CaretRight;
  const clamped = effective !== null && values.context_tokens > effective;
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
            {estimate(values, effective)}
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
                const rounds = field === "rounds";
                const note = rounds
                  ? "This server runs 1 round only."
                  : field === "context_tokens" && clamped
                    ? `${fmtN(values.context_tokens)} → ${fmtN(effective ?? 0)} (model window)`
                    : "";
                const NoteIcon = rounds ? LockSimple : Info;
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
                      value={rounds ? 1 : values[field]}
                      disabled={rounds}
                      onChange={(e) => {
                        if (!rounds) onEdit(field, Number(e.target.value) || min);
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
          </div>
        )}
      </div>
    </div>
  );
}

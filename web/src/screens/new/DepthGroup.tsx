// The Depth row of the Options panel: the preset control, its description and estimate, and the
// Advanced values. Editing a value switches to Custom. The action row saves Custom values as a
// preset (or into the user preset they came from) and deletes a user preset.
import { CaretDown, CaretRight, FloppyDisk, LockSimple, Plus, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import type { DepthInfo, ResearchValues } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
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

/** More user presets than this put all but the first two in the "More…" select. */
const MAX_USER_SEGMENTS = 3;
const SHOWN_USER_SEGMENTS = 2;

/** The action row's handlers. */
export type DepthActions = {
  /** Saves the Custom values into the user preset they came from. */
  onSaveTo: (preset: string) => void;
  onSaveAs: () => void;
  onDelete: (preset: string) => void;
};

type Props = {
  depth: Depth;
  /** Every preset from `GET /api/depths`. */
  presets: DepthInfo[];
  /** The preset whose values Custom started from by an edit. */
  customFrom?: string;
  description: string;
  values: ResearchValues;
  /** Files-only runs use one round. */
  filesOnly: boolean;
  onPick: (depth: Depth) => void;
  onEdit: (field: keyof ResearchValues, value: number) => void;
  actions: DepthActions;
};

export function DepthGroup({
  depth,
  presets,
  customFrom,
  description,
  values,
  filesOnly,
  onPick,
  onEdit,
  actions,
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
        <DepthSeg
          depth={depth}
          presets={presets}
          onPick={(d) => {
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
            <DepthActionRow
              depth={depth}
              presets={presets}
              customFrom={customFrom}
              actions={actions}
            />
          </div>
        )}
      </div>
    </div>
  );
}

type SegProps = { depth: Depth; presets: DepthInfo[]; onPick: (depth: Depth) => void };

/** Built-in presets, user presets (the extras in a "More…" select), then Custom. */
function DepthSeg({ depth, presets, onPick }: SegProps) {
  const builtin = presets.filter((p) => p.source !== "user").map((p) => p.name);
  const user = presets.filter((p) => p.source === "user").map((p) => p.name);
  const many = user.length > MAX_USER_SEGMENTS;
  const shown = many ? user.slice(0, SHOWN_USER_SEGMENTS) : user;
  const hidden = many ? user.slice(SHOWN_USER_SEGMENTS) : [];
  const hiddenPicked = hidden.includes(depth);
  const option = (d: Depth) => (
    <label key={d} className="seg-opt">
      <input type="radio" name="opt-depth" checked={depth === d} onChange={() => onPick(d)} />
      {depthLabel(d)}
    </label>
  );
  return (
    <div className={`seg ${css.wrapSeg}`} role="radiogroup" aria-label="Depth">
      {[...builtin, ...shown].map(option)}
      {many && (
        <label className={`seg-opt ${css.moreOpt}`}>
          <input
            type="radio"
            name="opt-depth"
            checked={hiddenPicked}
            tabIndex={-1}
            onChange={() => {}}
          />
          <select
            aria-label="More depth presets"
            value={hiddenPicked ? depth : ""}
            onChange={(e) => e.target.value && onPick(e.target.value)}
          >
            {!hiddenPicked && <option value="">More…</option>}
            {hidden.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
      )}
      {option("custom")}
    </div>
  );
}

type ActionProps = {
  depth: Depth;
  presets: DepthInfo[];
  customFrom?: string;
  actions: DepthActions;
};

/** Custom: Save to its user preset and Save as; a user preset: Delete. Built-ins show none. */
function DepthActionRow({ depth, presets, customFrom, actions }: ActionProps) {
  const userPreset = (name?: string) => presets.find((p) => p.name === name && p.source === "user");
  if (depth === "custom") {
    const from = userPreset(customFrom);
    return (
      <div className={css.actionRow}>
        {from?.managed && (
          <span className={css.lockNote}>
            <LockSimple aria-hidden="true" />
            {from.name} is managed by NixOS config
          </span>
        )}
        {from && !from.managed && (
          <button
            type="button"
            className={`btn btn-secondary ${css.actionBtn}`}
            onClick={() => actions.onSaveTo(from.name)}
          >
            <FloppyDisk aria-hidden="true" />
            Save to {from.name}
          </button>
        )}
        <button
          type="button"
          className={`btn btn-secondary ${css.actionBtn}`}
          onClick={actions.onSaveAs}
        >
          <Plus aria-hidden="true" />
          Save depth as…
        </button>
      </div>
    );
  }
  const selected = userPreset(depth);
  if (!selected) return null;
  return (
    <div className={css.actionRow}>
      {selected.managed ? (
        <span className={css.lockNote}>
          <LockSimple aria-hidden="true" />
          Managed by NixOS config · read-only
        </span>
      ) : (
        <span className={css.deleteSlot}>
          <button
            type="button"
            className={`btn btn-ghost ${css.deleteBtn}`}
            onClick={() => actions.onDelete(selected.name)}
          >
            <Trash aria-hidden="true" />
            Delete {selected.name}
          </button>
        </span>
      )}
    </div>
  );
}

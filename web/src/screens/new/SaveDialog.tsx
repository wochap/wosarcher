// "Save depth as…" and "Save profile as…" (scenarios `new-save-depth`, `new-save-profile`): a
// name checked as the server checks it, a profile's description, and what is saved.
import {
  FloppyDisk,
  Info,
  SlidersHorizontal,
  Stack,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { type FormEvent, useState } from "react";
import { ApiError } from "../../api/client";
import type {
  DepthSaveValues,
  ProfileInfo,
  ProviderEntry,
  ResearchValues,
  TokenBudget,
} from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { effectiveContext, effectiveGapContext, fmtN } from "../../run/depth";
import { nameError, type PresetKind } from "../../run/presets";
import {
  BLOCK_LABELS,
  BLOCKS,
  changedCount,
  limitsOf,
  type ProfileChoice,
  profileBase,
} from "../../run/profileValues";
import css from "./SaveDialog.module.css";

/** One "What is saved" group: a heading, label/value rows, and an optional note. */
export type SavedGroup = { title: string; rows: [string, string][]; note?: string };

const DEPTH_ROWS: [keyof ResearchValues, string][] = [
  ["sub_queries", "Sub-queries"],
  ["results_per_query", "Results per query"],
  ["max_pages", "Max pages"],
  ["rounds", "Rounds"],
  ["queries_per_round", "Follow-ups per round"],
  ["passages_per_query", "Passages per query"],
];

export function depthGroups(values: DepthSaveValues): SavedGroup[] {
  const rows = DEPTH_ROWS.map(([field, label]): [string, string] => [label, fmtN(values[field])]);
  rows.push(["Length", `${fmtN(values.words ?? 0)} words`]);
  return [{ title: "Depth values", rows }];
}

const budget = (value: TokenBudget, auto: number | null) =>
  value === "auto" ? `Auto${auto === null ? "" : ` · ${fmtN(auto)}`}` : fmtN(value);

/** The profile's entries, model and budget, and the chosen model's tuning, with the edits. */
export function profileGroups(
  profile: ProfileInfo | undefined,
  entries: ProviderEntry[],
  choice: ProfileChoice,
  words: number,
): SavedGroup[] {
  const base = profileBase(profile, entries, choice.use, choice.edits.model);
  const v = { ...base, ...choice.edits };
  const limits = limitsOf(v, profile);
  return [
    { title: "Entries", rows: BLOCKS.map((b) => [BLOCK_LABELS[b], base.use[b]]) },
    {
      title: "Model and budget",
      rows: [
        ["Model", `${base.use.llm} / ${v.model}`],
        ["Context tokens", budget(v.context_tokens, effectiveContext(limits, words))],
      ],
    },
    {
      title: `Model tuning for ${v.model}`,
      rows: [
        ["Context window", fmtN(v.context_window)],
        ["Max output", fmtN(v.max_output_tokens)],
        ["Thinking", `plan ${v.plan} · gap ${v.gap} · write ${v.write}`],
        ["Gap context", budget(v.gap_context_tokens, effectiveGapContext(limits))],
      ],
      note: `Applies only when this profile runs ${v.model}. With any other model, that model’s own entry limits apply.`,
    },
  ];
}

/** The intro of "Save profile as…": the base and the number of edits. */
export function profileIntro(base: string, choice: ProfileChoice): string {
  const n = changedCount(choice);
  const edits = n ? `, with your ${n} edit${n === 1 ? "" : "s"}` : "";
  return `Saves a new profile based on ${base}${edits}. ${base} itself is unchanged.`;
}

const DEPTH_INTRO =
  "Saves the six depth values and the report length as a new depth. It appears in Depth after the built-in presets.";

type Props = {
  kind: PresetKind;
  /** The names of that kind already taken. */
  existing: string[];
  /** The profile intro; a depth's is fixed. */
  intro?: string;
  groups: SavedGroup[];
  /** Saves; an `ApiError` keeps the dialog open with its detail as the name error. */
  onSave: (name: string, description: string) => Promise<void>;
  onClose: () => void;
};

export function SaveDialog({ kind, existing, intro, groups, onSave, onClose }: Props) {
  const profile = kind === "profile";
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);
  const found = nameError(name, kind, existing);
  const error = serverError || (found && (name.trim() || touched) ? found : "");
  const Icon = profile ? Stack : SlidersHorizontal;
  const title = profile ? "Save profile as…" : "Save depth as…";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (found || busy) {
      setTouched(true);
      return;
    }
    setBusy(true);
    try {
      await onSave(name.trim(), description.trim());
    } catch (failure) {
      setServerError(failure instanceof ApiError ? failure.message : String(failure));
      setBusy(false);
    }
  }

  return (
    <Dialog labelledBy="sv-t" onClose={onClose} className={css.dialog}>
      <form className={css.form} onSubmit={submit} noValidate>
        <div className={css.head}>
          <Icon className={css.icon} aria-hidden="true" />
          <div id="sv-t" className="dialog-title">
            {title}
          </div>
          <button
            type="button"
            className={`btn btn-ghost btn-icon ${css.close}`}
            aria-label="Close"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </button>
        </div>
        <p className={css.intro}>{profile ? intro : DEPTH_INTRO}</p>
        <div className={css.field}>
          <label htmlFor="sv-name" className={css.label}>
            Name
          </label>
          <input
            id="sv-name"
            className={`input ${css.name}`}
            value={name}
            autoFocus
            autoComplete="off"
            spellCheck={false}
            aria-invalid={!!error}
            aria-describedby="sv-msg"
            placeholder={profile ? "e.g. cloud-rerank" : "e.g. wide-short"}
            onChange={(e) => {
              setName(e.target.value);
              setServerError("");
            }}
          />
          {error ? (
            <span id="sv-msg" role="alert" className={css.error}>
              <WarningCircle aria-hidden="true" />
              {error}
            </span>
          ) : (
            <span id="sv-msg" className={css.hint}>
              Letters, digits, - and _ · up to 64 characters
            </span>
          )}
        </div>
        {profile && (
          <div className={css.field}>
            <label htmlFor="sv-desc" className={css.label}>
              Description <span className={css.faint}>· optional</span>
            </label>
            <input
              id="sv-desc"
              className="input"
              value={description}
              maxLength={120}
              placeholder="One line, shown under the profile"
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        )}
        <fieldset aria-label="What is saved" className={css.saved}>
          {groups.map((g) => (
            <div key={g.title} className={css.group}>
              <span className={css.groupTitle}>{g.title}</span>
              {g.rows.map(([k, v]) => (
                <div key={k} className={css.savedRow}>
                  <span className={css.muted}>{k}</span>
                  <span className={css.value}>{v}</span>
                </div>
              ))}
              {g.note && (
                <span className={css.note}>
                  <Info aria-hidden="true" />
                  {g.note}
                </span>
              )}
            </div>
          ))}
        </fieldset>
        <div className="dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            <FloppyDisk aria-hidden="true" />
            {profile ? "Save profile" : "Save depth"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

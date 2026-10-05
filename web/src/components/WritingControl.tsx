// One writing field's control: select, textarea, number, or segmented.
import { type ReactNode, useEffect, useState } from "react";
import { Seg } from "./Seg";
import {
  CITATION_MARKERS,
  capitalize,
  LANGUAGES,
  REFERENCE_STYLES,
  TONES,
  withCurrent,
} from "./tones";
import type { Props, WritingField } from "./WritingOptionsForm";
import css from "./WritingOptionsForm.module.css";

export function Control({
  value,
  onChange,
  field,
  id,
  idPrefix,
  compact,
  wordsHint,
}: Props & { field: WritingField; id: string }) {
  switch (field) {
    case "tone":
      return (
        <select
          id={id}
          className={`input ${css.select}`}
          value={value.tone}
          onChange={(e) => onChange("tone", e.target.value)}
        >
          {TONES.map((t) => (
            <option key={t.value} value={t.value}>
              {`${t.label} — ${t.description}`}
            </option>
          ))}
          {!TONES.some((t) => t.value === value.tone) && (
            <option value={value.tone}>{value.tone}</option>
          )}
        </select>
      );
    case "format":
      return (
        <Seg
          label="Format"
          name={`${idPrefix}-format`}
          value={value.format}
          options={[
            { value: "report", label: "report" },
            { value: "answer", label: "answer" },
          ]}
          onChange={(v) => onChange("format", v)}
        />
      );
    case "citation_marker":
      return (
        <Seg
          label="Citation marker"
          name={`${idPrefix}-cite`}
          value={value.citation_marker}
          options={CITATION_MARKERS}
          onChange={(v) => onChange("citation_marker", v)}
        />
      );
    case "tone_instructions":
      return (
        <Draft
          value={value.tone_instructions}
          commit={(v) => onChange("tone_instructions", v)}
          render={(draft, set, done) => (
            <textarea
              id={id}
              className={`input ${css.area}`}
              value={draft}
              placeholder="e.g. Focus on costs; avoid jargon."
              onChange={(e) => set(e.target.value)}
              onBlur={done}
            />
          )}
        />
      );
    case "words":
      return (
        <Draft
          value={String(value.words)}
          commit={(v) => onChange("words", Number(v) || 0)}
          render={(draft, set, done) => (
            <div className={css.number}>
              <input
                id={id}
                className="input"
                type="number"
                min={100}
                max={4000}
                step={50}
                value={draft}
                onChange={(e) => set(e.target.value)}
                onBlur={done}
                onKeyDown={(e) => e.key === "Enter" && done()}
              />
              <span className={css.unit}>{compact ? "words" : "words, approximately"}</span>
              {wordsHint && <span className={css.hint}>· {wordsHint}</span>}
            </div>
          )}
        />
      );
    case "language":
      return (
        <select
          id={id}
          className={`input ${css.select}`}
          value={value.language.toLowerCase()}
          onChange={(e) => onChange("language", e.target.value)}
        >
          {withCurrent(LANGUAGES, value.language).map((l) => (
            <option key={l} value={l.toLowerCase()}>
              {capitalize(l)}
            </option>
          ))}
        </select>
      );
    case "reference_style":
      return (
        <Seg
          label="Reference style"
          name={`${idPrefix}-ref`}
          value={listed(REFERENCE_STYLES, value.reference_style)}
          options={withCurrent(REFERENCE_STYLES, value.reference_style).map((s) => ({
            value: s,
            label: s,
          }))}
          onChange={(v) => onChange("reference_style", v)}
        />
      );
  }
}

/** The listed spelling of a case-insensitive value, or the value itself. */
function listed(values: string[], value: string): string {
  return values.find((v) => v.toLowerCase() === value.toLowerCase()) ?? value;
}

/** Typing edits a draft; `done` (blur, Enter) commits it, so "800" is one change, not three. */
function Draft({
  value,
  commit,
  render,
}: {
  value: string;
  commit: (value: string) => void;
  render: (draft: string, set: (v: string) => void, done: () => void) => ReactNode;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return render(draft, setDraft, () => draft !== value && commit(draft));
}

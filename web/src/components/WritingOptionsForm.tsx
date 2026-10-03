// The six writing fields in the prototype's form grid. Used by Settings (defaults), New run
// (marks "overridden" against the defaults), and the Rewrite dialog (marks "changed").
import type { WritingOptions } from "../api/types";
import { Tag } from "./Tag";
import { CITATION_MARKERS, capitalize } from "./tones";
import { Control } from "./WritingControl";
import css from "./WritingOptionsForm.module.css";

export type WritingField = keyof WritingOptions;

const LABELS: Record<WritingField, string> = {
  tone: "Tone",
  tone_instructions: "Custom tone instructions",
  words: "Target length",
  language: "Language",
  citation_marker: "Citation marker",
  reference_style: "Reference style",
};
const FIELDS = Object.keys(LABELS) as WritingField[];

/** How a value reads in "default: …" and "was …". */
export function describeValue(field: WritingField, value: WritingOptions[WritingField]): string {
  if (field === "citation_marker") {
    return CITATION_MARKERS.find((m) => m.value === value)?.label ?? String(value);
  }
  if (field === "tone_instructions") return value ? `“${value}”` : "none";
  if (field === "words") return `${value} words`;
  return capitalize(String(value));
}

export type Props = {
  value: WritingOptions;
  onChange: <F extends WritingField>(field: F, value: WritingOptions[F]) => void;
  base?: WritingOptions;
  mark?: "overridden" | "changed";
  baseLabel?: "default: " | "was ";
  idPrefix: string;
  compact?: boolean;
  errors?: Partial<Record<WritingField, string>>;
};

export function WritingOptionsForm(props: Props) {
  const { value, base, mark, baseLabel = "default: ", idPrefix, compact, errors = {} } = props;
  return (
    <div className={compact ? css.compact : undefined}>
      {FIELDS.map((field) => {
        const changed = !!base && String(value[field]) !== String(base[field]);
        const id = `${idPrefix}-${field}`;
        const segmented = field === "tone" || field === "citation_marker";
        const Label = segmented ? "span" : "label";
        return (
          <div key={field} className={css.row}>
            <div className={css.head}>
              <Label htmlFor={segmented ? undefined : id}>{LABELS[field]}</Label>
              {changed && base && (
                <>
                  <div className={css.marks}>
                    <Tag variant="outline" small>
                      {mark}
                    </Tag>
                    <button
                      type="button"
                      className={`btn btn-ghost ${css.reset}`}
                      onClick={() => props.onChange(field, base[field])}
                    >
                      Reset
                    </button>
                  </div>
                  <span className={css.base}>
                    {baseLabel}
                    {describeValue(field, base[field])}
                  </span>
                </>
              )}
            </div>
            <div className={css.control}>
              <Control {...props} field={field} id={id} />
              {errors[field] && (
                <div role="alert" className={css.error}>
                  {errors[field]}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

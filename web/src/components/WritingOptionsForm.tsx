// The six writing fields in the prototype's form grid. Used by Settings (defaults), New run
// (marks "overridden" against the defaults), and the Rewrite dialog (marks "changed"), which
// adds Format first; elsewhere the format is the Recipe or the Settings "Run defaults" row.
import type { WritingOptions } from "../api/types";
import { HelpTip } from "./HelpTip";
import { Tag } from "./Tag";
import { CITATION_MARKERS, capitalize } from "./tones";
import { Control } from "./WritingControl";
import css from "./WritingOptionsForm.module.css";

export type WritingField = keyof WritingOptions;

const LABELS: Record<WritingField, string> = {
  format: "Format",
  tone: "Tone",
  tone_instructions: "Custom instructions",
  words: "Length (words)",
  language: "Language",
  citation_marker: "Citation marker",
  reference_style: "Reference style",
};
const FIELDS = (Object.keys(LABELS) as WritingField[]).filter((f) => f !== "format");
const HELP_KEYS: Record<WritingField, string> = {
  format: "w-format",
  tone: "w-tone",
  tone_instructions: "w-custom",
  words: "w-words",
  language: "w-lang",
  citation_marker: "w-cite",
  reference_style: "w-ref",
};
const SHORT = 28;

/** How a value reads in "default: …" and "was …". */
export function describeValue(field: WritingField, value: WritingOptions[WritingField]): string {
  if (field === "citation_marker") {
    return CITATION_MARKERS.find((m) => m.value === value)?.label ?? String(value);
  }
  if (field === "tone_instructions") {
    const text = String(value);
    if (!text) return "none";
    return `“${text.length > SHORT ? `${text.slice(0, SHORT)}…` : text}”`;
  }
  if (field === "words") return `${value} words`;
  if (field === "format") return String(value);
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
  /** Length's base text when a depth sets its default ("Deep default: 2000 words"). */
  wordsBaseText?: string;
  /** Shown after Length's unit while it is not changed ("set by Deep"). */
  wordsHint?: string;
  /** Adds the Format field before the others (Rewrite dialog). */
  withFormat?: boolean;
};

export function WritingOptionsForm(props: Props) {
  const { value, base, mark, baseLabel = "default: ", idPrefix, compact, errors = {} } = props;
  const { wordsBaseText, wordsHint, withFormat } = props;
  return (
    <div className={compact ? css.compact : undefined}>
      {(withFormat ? (["format", ...FIELDS] as WritingField[]) : FIELDS).map((field) => {
        const changed = !!base && String(value[field]) !== String(base[field]);
        const id = `${idPrefix}-${field}`;
        const segmented =
          field === "format" || field === "citation_marker" || field === "reference_style";
        const Label = segmented ? "span" : "label";
        const depthBase = field === "words" && wordsBaseText;
        return (
          <div key={field} className={css.row}>
            <div className={css.head}>
              <div className={css.label}>
                <Label htmlFor={segmented ? undefined : id}>{LABELS[field]}</Label>
                <HelpTip help={HELP_KEYS[field]} />
              </div>
              {changed && base && (
                <>
                  <div className={css.marks}>
                    <span className={css.mark}>
                      <Tag variant="outline" small>
                        {mark}
                      </Tag>
                      <HelpTip
                        help={
                          depthBase
                            ? "w-words-def"
                            : mark === "changed"
                              ? "rwchanged"
                              : "overridden"
                        }
                      />
                    </span>
                    <button
                      type="button"
                      className={`btn btn-ghost ${css.reset}`}
                      onClick={() => props.onChange(field, base[field])}
                    >
                      Reset
                    </button>
                  </div>
                  <span className={css.base}>
                    {depthBase || `${baseLabel}${describeValue(field, base[field])}`}
                  </span>
                </>
              )}
            </div>
            <div className={css.control}>
              <Control
                {...props}
                field={field}
                id={id}
                wordsHint={field === "words" && !changed ? wordsHint : undefined}
              />
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

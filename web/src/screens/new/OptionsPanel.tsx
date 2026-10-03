// The collapsible Options panel of New run: run options and the writing options, which start
// from the saved defaults and mark per-run overrides.
import { ArrowCounterClockwise, CaretDown, CaretRight } from "@phosphor-icons/react";
import { type ReactNode, useState } from "react";
import type { WritingOptions } from "../../api/types";
import type { RunOptions } from "../../app/context";
import { go } from "../../app/route";
import { Seg } from "../../components/Seg";
import { type WritingField, WritingOptionsForm } from "../../components/WritingOptionsForm";
import { wSummary } from "../../run/format";
import css from "./OptionsPanel.module.css";

/** The fields of `value` that differ from `defaults`. */
export function overriddenFields(
  value: WritingOptions,
  defaults: WritingOptions,
): Partial<WritingOptions> {
  const fields = Object.keys(value) as WritingField[];
  return Object.fromEntries(
    fields.filter((f) => String(value[f]) !== String(defaults[f])).map((f) => [f, value[f]]),
  );
}

type Props = {
  options: RunOptions;
  profiles: string[];
  onOption: <K extends keyof RunOptions>(key: K, value: RunOptions[K]) => void;
  writing: WritingOptions;
  defaults: WritingOptions;
  onWriting: <F extends WritingField>(field: F, value: WritingOptions[F]) => void;
  onResetWriting: () => void;
};

export function OptionsPanel(props: Props) {
  const { options, profiles, onOption, writing, defaults } = props;
  const [open, setOpen] = useState(false);
  const overridden = Object.keys(overriddenFields(writing, defaults)).length;
  const Caret = open ? CaretDown : CaretRight;
  const summary = `${options.recipe} · ${options.sources} · ${options.profile} · ${wSummary(writing)}`;
  return (
    <div className={css.panel}>
      <button
        type="button"
        className={css.toggle}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Caret className={css.caret} aria-hidden="true" />
        <span className={css.title}>Options</span>
        <span className={css.summary}>{summary}</span>
        {overridden > 0 && (
          <span className={`tag tag-outline ${css.count}`}>{overridden} overridden</span>
        )}
      </button>
      {open && (
        <div className={css.body}>
          <div className={css.group}>Run</div>
          <Row label="Recipe">
            <Seg
              label="Recipe"
              name="opt-recipe"
              value={options.recipe}
              options={[
                { value: "context", label: "context" },
                { value: "report", label: "report" },
              ]}
              onChange={(v) => onOption("recipe", v)}
            />
          </Row>
          <Row label="Sources">
            <Seg
              label="Sources"
              name="opt-sources"
              value={options.sources}
              options={(["web", "files", "both"] as const).map((v) => ({ value: v, label: v }))}
              onChange={(v) => onOption("sources", v)}
            />
          </Row>
          <Row label="Profile">
            <Seg
              label="Profile"
              name="opt-profile"
              value={options.profile}
              options={profiles.map((p) => ({ value: p, label: p }))}
              onChange={(v) => onOption("profile", v)}
            />
          </Row>
          <div className={css.writingHead}>
            <span className={css.group}>Writing</span>
            <span className={css.note}>Preselected from your defaults ·</span>
            <button
              type="button"
              className={`btn btn-ghost ${css.link}`}
              onClick={() => go({ screen: "settings" })}
            >
              edit defaults
            </button>
            {overridden > 0 && (
              <button
                type="button"
                className={`btn btn-ghost ${css.link} ${css.resetAll}`}
                onClick={props.onResetWriting}
              >
                <ArrowCounterClockwise aria-hidden="true" />
                Reset all to defaults
              </button>
            )}
          </div>
          <WritingOptionsForm
            idPrefix="nw"
            value={writing}
            base={defaults}
            mark="overridden"
            baseLabel="default: "
            onChange={props.onWriting}
          />
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={css.row}>
      <span className={css.rowLabel}>{label}</span>
      {children}
    </div>
  );
}

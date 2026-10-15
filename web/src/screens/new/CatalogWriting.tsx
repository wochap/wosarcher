// The catalog form's Writing panel, shown under the Structure panel when Output is Report or
// Both: the research form's Writing group with the saved writing defaults as its base.
import { ArrowCounterClockwise } from "@phosphor-icons/react";
import type { WritingOptions } from "../../api/types";
import { go } from "../../app/route";
import { type WritingField, WritingOptionsForm } from "../../components/WritingOptionsForm";
import { overriddenFields } from "./OptionsPanel";
import css from "./StructurePanel.module.css";

type Props = {
  value: WritingOptions;
  defaults: WritingOptions;
  onChange: <F extends WritingField>(field: F, value: WritingOptions[F]) => void;
  onReset: () => void;
};

export function CatalogWriting({ value, defaults, onChange, onReset }: Props) {
  const overridden = Object.keys(overriddenFields(value, defaults)).length > 0;
  return (
    // biome-ignore lint/a11y/useSemanticElements: the prototype's labelled group of controls
    <div role="group" aria-label="Writing" className={css.panel}>
      <div className={css.writingHead}>
        <span className={css.group}>Writing</span>
        <span className={css.faintNote}>Preselected from your defaults ·</span>
        <button
          type="button"
          className={`btn btn-ghost ${css.link}`}
          onClick={() => go({ screen: "settings" })}
        >
          edit defaults
        </button>
        {overridden && (
          <button
            type="button"
            className={`btn btn-ghost ${css.link} ${css.resetAll}`}
            onClick={onReset}
          >
            <ArrowCounterClockwise aria-hidden="true" />
            Reset all to defaults
          </button>
        )}
      </div>
      <WritingOptionsForm
        idPrefix="cw"
        value={value}
        base={defaults}
        mark="overridden"
        baseLabel="default: "
        onChange={onChange}
      />
    </div>
  );
}

// The Model group at the end of the Advanced values: the chat model and a thinking level per
// step. Editing these does not switch the depth to Custom.
import { Info, LockSimple } from "@phosphor-icons/react";
import type { Effort } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
import {
  EFFORT_LABELS,
  EFFORTS,
  type LlmValues,
  STEP_LABELS,
  STEPS,
  type Step,
} from "../../run/thinking";
import css from "./OptionsPanel.module.css";

type Props = {
  values: LlmValues;
  /** IDs the profile's endpoint lists, offered as suggestions. */
  models: string[];
  /** Gap thinking is used only between rounds. */
  rounds: number;
  onChange: (values: LlmValues) => void;
};

export function ModelGroup({ values, models, rounds, onChange }: Props) {
  const setLevel = (step: Step, level: Effort) =>
    onChange({ ...values, reasoning: { ...values.reasoning, [step]: level } });
  return (
    <>
      <span className={css.advNote}>Model</span>
      <div className={css.advGrid}>
        <div className={css.advField}>
          <div className={css.advLabel}>
            <label htmlFor="m-model">Model</label>
            <HelpTip help="model" />
          </div>
          <input
            id="m-model"
            className={`input ${css.advInput}`}
            list="m-models"
            placeholder="profile default"
            value={values.model}
            onChange={(e) => onChange({ ...values, model: e.target.value })}
          />
          <datalist id="m-models">
            {models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>
        {STEPS.map((step) => {
          const locked = step === "gap" && rounds === 1;
          const NoteIcon = locked ? LockSimple : Info;
          return (
            <div key={step} className={css.advField}>
              <div className={css.advLabel}>
                <label htmlFor={`m-${step}`}>{`${STEP_LABELS[step]} thinking`}</label>
                <HelpTip help="thinking" />
              </div>
              <select
                id={`m-${step}`}
                className={`input ${css.advInput}`}
                value={values.reasoning[step]}
                disabled={locked}
                onChange={(e) => setLevel(step, e.target.value as Effort)}
              >
                {EFFORTS.map((level) => (
                  <option key={level} value={level}>
                    {EFFORT_LABELS[level]}
                  </option>
                ))}
              </select>
              {locked && (
                <span className={css.advFieldNote}>
                  <NoteIcon aria-hidden="true" />
                  Used between rounds; needs 2+ rounds.
                </span>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

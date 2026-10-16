// The "Questions" row of both run forms: Ask or Don't ask, and while asking the timeout, preselected
// from Settings with the overridden mark and Reset.

import type { QuestionsOptions } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
import { Seg } from "../../components/Seg";
import { Tag } from "../../components/Tag";
import { type AskDraft, askView, clampTimeout, MAX_TIMEOUT } from "../../run/ask";
import css from "./QuestionsRow.module.css";

type Props = {
  /** Distinguishes the ids of the research and catalog forms. */
  idPrefix: string;
  value: AskDraft;
  defaults: QuestionsOptions;
  onChange: (value: AskDraft) => void;
};

export function QuestionsRow({ idPrefix, value, defaults, onChange }: Props) {
  const view = askView(value, defaults);
  const labelId = `${idPrefix}-q-l`;
  return (
    <div className={css.row}>
      <div className={css.head}>
        <div className={css.label}>
          <span id={labelId}>Questions</span>
          <HelpTip help="q-ask" label="Questions" />
        </div>
        {view.changed && (
          <>
            <div className={css.marks}>
              <span className={css.mark}>
                <Tag variant="outline" small>
                  overridden
                </Tag>
                <HelpTip help="q-over" label="Overridden" />
              </span>
              <button
                type="button"
                className={`btn btn-ghost ${css.reset}`}
                onClick={() => onChange({})}
              >
                Reset
              </button>
            </div>
            <span className={css.base}>{view.base}</span>
          </>
        )}
      </div>
      <div className={css.control}>
        <Seg
          label="Questions"
          name={`${idPrefix}-q-ask`}
          value={view.ask ? "ask" : "no"}
          options={[
            { value: "ask", label: "Ask" },
            { value: "no", label: "Don’t ask" },
          ]}
          onChange={(v) => onChange({ ...value, ask: v === "ask" })}
        />
        {view.ask && (
          <span className={css.timeout}>
            <label htmlFor={`${idPrefix}-q-t`}>Timeout</label>
            <input
              id={`${idPrefix}-q-t`}
              className="input"
              type="number"
              min={0}
              max={MAX_TIMEOUT}
              step={5}
              value={view.timeout}
              onChange={(e) => onChange({ ...value, timeout: clampTimeout(e.target.value) })}
            />
            <span className={css.unit}>s</span>
          </span>
        )}
      </div>
    </div>
  );
}

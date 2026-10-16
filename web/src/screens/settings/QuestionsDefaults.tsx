// Settings: the Run questions defaults (ask before searching, between rounds, timeout when idle),
// saved on every change with PUT /api/settings. `max_wait` rides along unchanged.
import { Check } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import type { QuestionsOptions, ServerSettings } from "../../api/types";
import { useApi } from "../../app/context";
import { HelpTip } from "../../components/HelpTip";
import page from "../../components/Page.module.css";
import { Switch } from "../../components/Switch";
import { MAX_TIMEOUT } from "../../run/ask";
import css from "./QuestionsDefaults.module.css";
import { SAVED_MS, type SettingsProps } from "./WritingDefaults";
import writing from "./WritingDefaults.module.css";

type Field = "clarify" | "rounds" | "timeout";

/** A typed timeout when it is a whole number from 0 to 3600; else null. */
export function validTimeout(text: string): number | null {
  if (!/^\d+$/.test(text.trim())) return null;
  const value = Number(text);
  return value <= MAX_TIMEOUT ? value : null;
}

export function QuestionsDefaults({ settings, setSettings }: SettingsProps) {
  const api = useApi();
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  if (!settings) return null;
  const current = settings;
  const q = current.questions;
  const typed = text ?? String(q.timeout);
  const invalid = validTimeout(typed) === null;

  async function save<F extends Field>(field: F, value: QuestionsOptions[F]) {
    const next: ServerSettings = {
      ...current,
      questions: { ...current.questions, [field]: value },
    };
    setSettings(next);
    setError("");
    try {
      await api.putSettings(next);
      setSaved(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setSaved(false), SAVED_MS);
    } catch (e) {
      setSettings((s) => s && { ...s, questions: { ...s.questions, [field]: q[field] } });
      setError(e instanceof ApiError ? (e.fields[`questions.${field}`] ?? e.message) : String(e));
    }
  }

  function type(value: string) {
    setText(value);
    const timeout = validTimeout(value);
    if (timeout !== null && timeout !== q.timeout) void save("timeout", timeout);
  }

  return (
    <>
      <div className={writing.header}>
        <h2 className={page.section}>Run questions</h2>
        <span className={writing.note}>Preselected on every new run · saved automatically</span>
        {saved && (
          <span className={writing.saved}>
            <Check aria-hidden="true" />
            Saved
          </span>
        )}
      </div>
      <div className={`${page.panel} ${writing.panel}`}>
        {(
          [
            ["clarify", "Ask before searching", "q-clarify"],
            ["rounds", "Ask between rounds", "q-rounds"],
          ] as const
        ).map(([field, label, help]) => (
          <div key={field} className={css.row}>
            <div className={css.label}>
              <span id={`sq-${field}-l`}>{label}</span>
              <HelpTip help={help} label={label} />
            </div>
            <div className={css.control}>
              <Switch
                on={q[field]}
                labelledBy={`sq-${field}-l`}
                onToggle={() => void save(field, !q[field])}
              />
            </div>
          </div>
        ))}
        <div className={css.row}>
          <div className={css.label}>
            <label htmlFor="sq-timeout">Timeout when idle</label>
            <HelpTip help="q-timeout" label="Timeout when idle" />
          </div>
          <div className={css.control}>
            <input
              id="sq-timeout"
              className={`input ${css.number}`}
              type="number"
              min={0}
              max={MAX_TIMEOUT}
              step={5}
              value={typed}
              aria-invalid={invalid}
              onChange={(e) => type(e.target.value)}
              onBlur={() => setText(null)}
            />
            <span className={css.unit}>seconds</span>
            <span className={css.hint}>
              · {q.timeout === 0 ? "0 continues at once" : "counts down only while you are away"}
            </span>
          </div>
        </div>
        {invalid && <div className={css.error}>Use a whole number from 0 to {MAX_TIMEOUT}.</div>}
        {error && (
          <div role="alert" className={css.error}>
            {error}
          </div>
        )}
      </div>
    </>
  );
}

// Settings: the server's writing defaults, saved on every change (PUT /api/settings).
import { Check } from "@phosphor-icons/react";
import { type Dispatch, type SetStateAction, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import type { ServerSettings, WritingOptions } from "../../api/types";
import { useApi } from "../../app/context";
import { HelpTip } from "../../components/HelpTip";
import page from "../../components/Page.module.css";
import { type WritingField, WritingOptionsForm } from "../../components/WritingOptionsForm";
import css from "./WritingDefaults.module.css";

export const SAVED_MS = 1500;

/** The settings Settings loaded, shared by its sections so each saves the others' latest values. */
export type SettingsProps = {
  settings: ServerSettings | null;
  setSettings: Dispatch<SetStateAction<ServerSettings | null>>;
};

export function WritingDefaults({ settings, setSettings }: SettingsProps) {
  const api = useApi();
  const [errors, setErrors] = useState<Partial<Record<WritingField, string>>>({});
  const [saved, setSaved] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  if (!settings) return null;
  const current = settings;

  async function change<F extends WritingField>(field: F, value: WritingOptions[F]) {
    const next = { ...current, writing: { ...current.writing, [field]: value } };
    setSettings(next);
    setErrors((e) => ({ ...e, [field]: undefined }));
    try {
      await api.putSettings(next);
      setSaved(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setSaved(false), SAVED_MS);
    } catch (e) {
      const message =
        e instanceof ApiError ? (e.fields[`writing.${field}`] ?? e.message) : String(e);
      setSettings((s) => s && { ...s, writing: { ...s.writing, [field]: current.writing[field] } });
      setErrors((errs) => ({ ...errs, [field]: message }));
    }
  }

  return (
    <>
      <div className={css.header}>
        <h2 className={page.section}>Writing defaults</h2>
        <HelpTip help="wdefaults" />
        <span className={css.note}>Preselected on every new run · saved automatically</span>
        {saved && (
          <span className={css.saved}>
            <Check aria-hidden="true" />
            Saved
          </span>
        )}
      </div>
      <div className={`${page.panel} ${css.panel}`}>
        <WritingOptionsForm
          idPrefix="df"
          value={settings.writing}
          onChange={change}
          errors={errors}
        />
      </div>
    </>
  );
}

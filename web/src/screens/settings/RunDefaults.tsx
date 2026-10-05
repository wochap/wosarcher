// Settings: the server's global domain lists, saved on every change (PUT /api/settings).
import { Check, Info } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import type { ProfileInfo } from "../../api/types";
import { useApi } from "../../app/context";
import { type DomainKind, DomainRows } from "../../components/DomainRows";
import { HelpTip } from "../../components/HelpTip";
import page from "../../components/Page.module.css";
import { SAVED_MS, type SettingsProps } from "./WritingDefaults";
import css from "./WritingDefaults.module.css";

/** The note naming the profiles that set their own lists; empty when none does. */
export function profilesNote(profiles: ProfileInfo[]): string {
  const names = profiles.filter((p) => p.allow_domains || p.block_domains).map((p) => p.name);
  if (!names.length) return "";
  return `The ${names.join(" and ")} profiles set their own domain lists; runs on those profiles use them instead.`;
}

export function RunDefaults({ settings, setSettings }: SettingsProps) {
  const api = useApi();
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [errors, setErrors] = useState<Partial<Record<DomainKind, string>>>({});
  const [saved, setSaved] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    api.listProfiles().then(setProfiles, () => {});
    return () => clearTimeout(timer.current);
  }, [api]);

  if (!settings) return null;
  const current = settings;

  async function change(kind: DomainKind, list: string[] | null) {
    const next = { ...current, domains: { ...current.domains, [kind]: list ?? [] } };
    setSettings(next);
    setErrors((e) => ({ ...e, [kind]: undefined }));
    try {
      await api.putSettings(next);
      setSaved(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setSaved(false), SAVED_MS);
    } catch (e) {
      const message =
        e instanceof ApiError ? (e.fields[`domains.${kind}`] ?? e.message) : String(e);
      setSettings((s) => s && { ...s, domains: { ...s.domains, [kind]: current.domains[kind] } });
      setErrors((errs) => ({ ...errs, [kind]: message }));
    }
  }

  const note = profilesNote(profiles);
  return (
    <>
      <div className={css.header}>
        <h2 className={page.section}>Run defaults</h2>
        <HelpTip help="rdefaults" />
        <span className={css.note}>Preselected on every new run · saved automatically</span>
        {saved && (
          <span className={css.saved}>
            <Check aria-hidden="true" />
            Saved
          </span>
        )}
      </div>
      <div className={`${page.panel} ${css.panel}`}>
        <DomainRows
          idPrefix="sd"
          lists={settings.domains}
          onChange={(kind, list) => void change(kind, list)}
          errors={errors}
          spacious
        />
        {note && (
          <div className={css.profilesNote}>
            <Info aria-hidden="true" className={css.noteIcon} />
            <span>{note}</span>
          </div>
        )}
      </div>
    </>
  );
}

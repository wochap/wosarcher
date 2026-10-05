// Settings: the server's default format and global domain lists, saved on every change
// (PUT /api/settings).
import { Check, Info, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import type { ProfileInfo, ServerSettings, WritingOptions } from "../../api/types";
import { useApi } from "../../app/context";
import { type DomainKind, DomainRows } from "../../components/DomainRows";
import rows from "../../components/DomainRows.module.css";
import { HelpTip } from "../../components/HelpTip";
import page from "../../components/Page.module.css";
import { Seg } from "../../components/Seg";
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
  const [errors, setErrors] = useState<Partial<Record<DomainKind | "format", string>>>({});
  const [saved, setSaved] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    api.listProfiles().then(setProfiles, () => {});
    return () => clearTimeout(timer.current);
  }, [api]);

  if (!settings) return null;
  const current = settings;

  /** Saves `next`; a rejected value shows the server's error under its row and is restored. */
  async function save(row: DomainKind | "format", field: string, next: ServerSettings) {
    setSettings(next);
    setErrors((e) => ({ ...e, [row]: undefined }));
    try {
      await api.putSettings(next);
      setSaved(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setSaved(false), SAVED_MS);
    } catch (e) {
      const message = e instanceof ApiError ? (e.fields[field] ?? e.message) : String(e);
      setSettings((s) =>
        s && row === "format"
          ? { ...s, writing: { ...s.writing, format: current.writing.format } }
          : s && { ...s, domains: { ...s.domains, [row]: current.domains[row as DomainKind] } },
      );
      setErrors((errs) => ({ ...errs, [row]: message }));
    }
  }

  const changeDomains = (kind: DomainKind, list: string[] | null) =>
    save(kind, `domains.${kind}`, {
      ...current,
      domains: { ...current.domains, [kind]: list ?? [] },
    });
  const changeFormat = (format: WritingOptions["format"]) =>
    save("format", "writing.format", { ...current, writing: { ...current.writing, format } });

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
        <div className={`${rows.row} ${rows.spacious}`}>
          <div className={rows.head}>
            <div className={rows.label}>
              <span id="sd-format-l">Format</span>
              <HelpTip help="w-format" />
            </div>
          </div>
          <div className={`${rows.control} ${css.formatControl}`}>
            <Seg
              label="Format"
              name="sd-format"
              value={settings.writing.format}
              options={[
                { value: "report", label: "report" },
                { value: "answer", label: "answer" },
              ]}
              onChange={(v) => void changeFormat(v)}
            />
            {errors.format && (
              <span role="alert" className={rows.error}>
                <WarningCircle aria-hidden="true" className={rows.errorIcon} />
                {errors.format}
              </span>
            )}
            <span className={rows.hint}>
              Preselects the Recipe on New run. Context is chosen per run.
            </span>
          </div>
        </div>
        <DomainRows
          idPrefix="sd"
          lists={settings.domains}
          onChange={(kind, list) => void changeDomains(kind, list)}
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

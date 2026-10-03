// New run: the question, attachments, and options; starts the run and opens it on Live run.
import { Play } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { ProfileInfo, RunCreate, ServerSettings, WritingOptions } from "../../api/types";
import { EMPTY_DRAFT, type RunOptions, useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import type { WritingField } from "../../components/WritingOptionsForm";
import { Attachments } from "./Attachments";
import css from "./NewRunScreen.module.css";
import { OptionsPanel, overriddenFields } from "./OptionsPanel";

/** The request for `draft`: the context recipe stops after select; writing holds overrides. */
export function runRequest(
  query: string,
  options: RunOptions,
  writing: WritingOptions,
  defaults: WritingOptions,
): RunCreate {
  const request: RunCreate = { query, sources: options.sources, profile: options.profile };
  if (options.recipe === "context") request.until = "select";
  const overrides = overriddenFields(writing, defaults);
  if (Object.keys(overrides).length) request.writing = overrides;
  return request;
}

export function NewRunScreen() {
  const api = useApi();
  const { draft, setDraft, follow } = useUi();
  const [settings, setSettings] = useState<ServerSettings | null>(null);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const question = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    question.current?.focus();
    api.getSettings().then(setSettings, () => {});
    api.listProfiles().then(setProfiles, () => {});
  }, [api]);

  const active = profiles.find((p) => p.active)?.name ?? profiles[0]?.name ?? "";
  const options: RunOptions = {
    recipe: "report",
    sources: (settings?.sources as RunOptions["sources"] | undefined) ?? "both",
    profile: active,
    ...draft.options,
  };
  const defaults = settings?.writing;
  const writing = defaults && { ...defaults, ...draft.writing };
  const blank = !draft.query.trim();

  async function start() {
    if (blank || busy || !defaults || !writing) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.createRun(
        runRequest(draft.query.trim(), options, writing, defaults),
        draft.files,
      );
      setDraft(() => EMPTY_DRAFT);
      follow(created.run_id);
      go({ screen: "live", runId: created.run_id });
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  /** A value equal to its default is no override, so later default changes reach it. */
  function setWriting<F extends WritingField>(field: F, value: WritingOptions[F]) {
    setDraft((d) => {
      const { [field]: _, ...rest } = d.writing;
      const same = defaults && String(defaults[field]) === String(value);
      return { ...d, writing: same ? rest : { ...rest, [field]: value } };
    });
  }

  const profileNames = profiles.length ? profiles.map((p) => p.name) : [options.profile];
  return (
    <div className={css.page}>
      <div className={css.inner}>
        <div>
          <h1 className={css.h1}>New research run</h1>
          <p className={css.intro}>
            wosarcher searches the web and your files, scores passages for relevance, and writes a
            cited report.
          </p>
        </div>
        <div className="field">
          <label htmlFor="q">Question</label>
          <textarea
            id="q"
            ref={question}
            className={`input ${css.question}`}
            rows={6}
            value={draft.query}
            placeholder="e.g. How do speculative decoding methods trade off acceptance rate against draft-model size on 12 GB GPUs?"
            onChange={(e) => setDraft((d) => ({ ...d, query: e.target.value }))}
            onKeyDown={(e) => {
              if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault();
                void start();
              }
            }}
          />
          <div className={css.actions}>
            <span className={css.hint}>
              <kbd>Ctrl</kbd>+<kbd>Enter</kbd>to run
            </span>
            <button
              type="button"
              className={`btn btn-primary ${css.run}`}
              disabled={blank || busy}
              onClick={() => void start()}
            >
              <Play aria-hidden="true" />
              Run research
            </button>
          </div>
          {error && (
            <div role="alert" className={css.error}>
              {error}
            </div>
          )}
        </div>
        <Attachments files={draft.files} onChange={(files) => setDraft((d) => ({ ...d, files }))} />
        {defaults && writing && (
          <OptionsPanel
            options={options}
            profiles={profileNames}
            onOption={(key, value) =>
              setDraft((d) => ({ ...d, options: { ...d.options, [key]: value } }))
            }
            writing={writing}
            defaults={defaults}
            onWriting={setWriting}
            onResetWriting={() => setDraft((d) => ({ ...d, writing: {} }))}
          />
        )}
      </div>
    </div>
  );
}

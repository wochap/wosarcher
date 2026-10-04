// New run: the question, attachments, and options; starts the run and opens it on Live run.
import { Play } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type {
  DepthInfo,
  ProfileInfo,
  ResearchValues,
  RunCreate,
  ServerSettings,
  WritingOptions,
} from "../../api/types";
import { EMPTY_DRAFT, type RunOptions, useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import type { WritingField } from "../../components/WritingOptionsForm";
import {
  CUSTOM_DESCRIPTION,
  type Depth,
  effectiveContext,
  loadCustom,
  researchOf,
  saveCustom,
} from "../../run/depth";
import { Attachments } from "./Attachments";
import css from "./NewRunScreen.module.css";
import { OptionsPanel, overriddenFields } from "./OptionsPanel";

/**
 * The request for the form: the context recipe stops after select; writing holds overrides of
 * the depth-aware `defaults`. Custom sends its six values, and Length whenever it differs from
 * the saved default, since no preset sets it on the server.
 */
export function runRequest(
  query: string,
  options: RunOptions,
  writing: WritingOptions,
  defaults: WritingOptions,
  saved: WritingOptions,
  custom?: ResearchValues,
): RunCreate {
  const request: RunCreate = {
    query,
    sources: options.sources,
    profile: options.profile,
    depth: options.depth,
  };
  if (options.recipe === "context") request.until = "select";
  const overrides = overriddenFields(writing, defaults);
  if (options.depth === "custom") {
    if (custom) request.research = custom;
    if (writing.words !== saved.words) overrides.words = writing.words;
  }
  if (Object.keys(overrides).length) request.writing = overrides;
  return request;
}

export function NewRunScreen() {
  const api = useApi();
  const { draft, setDraft, follow } = useUi();
  const [settings, setSettings] = useState<ServerSettings | null>(null);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [depths, setDepths] = useState<DepthInfo[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const question = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    question.current?.focus();
    api.getSettings().then(setSettings, () => {});
    api.listProfiles().then(setProfiles, () => {});
    api.listDepths().then(setDepths, () => {});
  }, [api]);

  const active = profiles.find((p) => p.active)?.name ?? profiles[0]?.name ?? "";
  const options: RunOptions = {
    recipe: "report",
    sources: (settings?.sources as RunOptions["sources"] | undefined) ?? "both",
    profile: active,
    depth: "standard",
    ...draft.options,
  };
  const saved = settings?.writing;
  const presetOf = (d: Depth) => depths.find((info) => info.name === d);
  const standard = presetOf("standard");
  const valuesOf = (d: Depth) => {
    if (d === "custom") return draft.custom?.values;
    const info = presetOf(d) ?? standard;
    return info && researchOf(info);
  };
  const wordsOf = (d: Depth) =>
    (d === "custom" ? draft.custom?.words : presetOf(d)?.values.words) ?? saved?.words;
  const values = valuesOf(options.depth);
  const defaults = saved && { ...saved, words: wordsOf(options.depth) ?? saved.words };
  const writing = defaults && { ...defaults, ...draft.writing };
  const blank = !draft.query.trim();

  async function start() {
    if (blank || busy || !defaults || !writing) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.createRun(
        runRequest(draft.query.trim(), options, writing, defaults, saved ?? defaults, values),
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

  /** Switches the depth; Length keeps an edit unless it equals the new depth's default. */
  function pickDepth(depth: Depth) {
    setDraft((d) => {
      const custom =
        depth === "custom" && !d.custom && values
          ? { values: { ...values, ...loadCustom() }, words: wordsOf(options.depth) ?? 0 }
          : d.custom;
      const base = depth === "custom" ? custom?.words : wordsOf(depth);
      const { words, ...rest } = d.writing;
      const writing = words === undefined || words === base ? rest : d.writing;
      return { ...d, custom, writing, options: { ...d.options, depth } };
    });
  }

  /** Editing an Advanced value switches to Custom with the values shown, the edit applied. */
  function editResearch(field: keyof ResearchValues, value: number) {
    if (!values) return;
    const next = { ...values, [field]: value };
    saveCustom(next);
    setDraft((d) => ({
      ...d,
      custom: {
        values: next,
        words:
          d.custom && options.depth === "custom" ? d.custom.words : (wordsOf(options.depth) ?? 0),
      },
      options: { ...d.options, depth: "custom" },
    }));
  }

  /** A value equal to its default is no override, so later default changes reach it. */
  function setWriting<F extends WritingField>(field: F, value: WritingOptions[F]) {
    setDraft((d) => {
      const { [field]: _, ...rest } = d.writing;
      const same = defaults && String(defaults[field]) === String(value);
      return { ...d, writing: same ? rest : { ...rest, [field]: value } };
    });
  }

  const profileList: ProfileInfo[] = profiles.length
    ? profiles
    : [{ name: options.profile, source: "builtin", active: true, description: "" }];
  const profile = profileList.find((p) => p.name === options.profile);
  const depthNames = depths.map((info) => info.name as Depth);
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
        {defaults && writing && values && (
          <OptionsPanel
            options={options}
            profiles={profileList}
            depth={{
              depths: [...depthNames, "custom"],
              description:
                options.depth === "custom"
                  ? CUSTOM_DESCRIPTION
                  : (presetOf(options.depth)?.description ?? ""),
              values,
              effective: effectiveContext(profile, writing.words),
              queriesPerRound:
                (presetOf(options.depth) ?? depths[depths.length - 1])?.values.queries_per_round ??
                3,
              wordsSet: options.depth === "custom" || presetOf(options.depth)?.values.words != null,
              onPick: pickDepth,
              onEdit: editResearch,
            }}
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

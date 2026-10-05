// New run: the question, attachments, and options; starts the run and opens it on Live run.
import { Play, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import type {
  DepthInfo,
  DomainLists,
  ProfileInfo,
  ResearchValues,
  RunCreate,
  ServerSettings,
  TokenBudget,
  WritingOptions,
} from "../../api/types";
import { EMPTY_DRAFT, type RunOptions, useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import {
  DOMAIN_KINDS,
  type DomainKind,
  domainInputId,
  isDomain,
  sameList,
} from "../../components/DomainRows";
import type { WritingField } from "../../components/WritingOptionsForm";
import {
  CUSTOM_DESCRIPTION,
  type Depth,
  effectiveContext,
  effectiveGapContext,
  loadCustom,
  researchOf,
  saveCustom,
} from "../../run/depth";
import { Attachments } from "./Attachments";
import css from "./NewRunScreen.module.css";
import {
  isSearchLanguage,
  OptionsPanel,
  overriddenDomains,
  overriddenFields,
} from "./OptionsPanel";

/** Why the server (or the entry check) refused the run; `field` names a domain row to fix. */
type StartError = { message: string; field?: DomainKind; entry?: string };

/** The first entry that is not a domain, as the server would reject it. */
export function invalidDomain(lists: DomainLists): StartError | null {
  for (const field of DOMAIN_KINDS) {
    const entry = lists[field].find((e) => !isDomain(e));
    if (entry !== undefined) {
      const message = `domains.${field}: '${entry}' is not a domain; use the domain only, without a scheme, path, or port`;
      return { message, field, entry };
    }
  }
  return null;
}

/** The start error for a failed request; a rejected domain list names its row and entry. */
function startError(error: unknown): StartError {
  const message = (error as Error).message;
  if (!(error instanceof ApiError)) return { message };
  const field = DOMAIN_KINDS.find((k) => `domains.${k}` in error.fields);
  if (!field) return { message };
  const entry = /'([^']*)'/.exec(error.fields[`domains.${field}`])?.[1];
  return { message, field, entry };
}

/**
 * The request for the form: the context recipe stops after select, and the report and answer
 * recipes send their `writing.format`; writing also holds overrides of
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
  domains: Partial<DomainLists> = {},
  searchLanguage = "",
): RunCreate {
  const request: RunCreate = {
    query,
    sources: options.sources,
    profile: options.profile,
    depth: options.depth,
  };
  const overrides = overriddenFields(writing, defaults);
  if (options.recipe === "context") request.until = "select";
  else overrides.format = options.recipe;
  if (options.depth === "custom") {
    if (custom) request.research = custom;
    if (writing.words !== saved.words) overrides.words = writing.words;
  }
  if (Object.keys(overrides).length) request.writing = overrides;
  if (Object.keys(domains).length) request.domains = domains;
  if (searchLanguage.trim()) request.search_language = searchLanguage.trim();
  return request;
}

export function NewRunScreen() {
  const api = useApi();
  const { draft, setDraft, follow } = useUi();
  const [settings, setSettings] = useState<ServerSettings | null>(null);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [depths, setDepths] = useState<DepthInfo[]>([]);
  const [error, setError] = useState<StartError | null>(null);
  const [busy, setBusy] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [focusField, setFocusField] = useState<DomainKind | null>(null);
  const question = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!focusField || !optionsOpen) return;
    document.getElementById(domainInputId("nd", focusField))?.focus();
    setFocusField(null);
  }, [focusField, optionsOpen]);

  useEffect(() => {
    question.current?.focus();
    api.getSettings().then(setSettings, () => {});
    api.listProfiles().then(setProfiles, () => {});
    api.listDepths().then(setDepths, () => {});
  }, [api]);

  const active = profiles.find((p) => p.active)?.name ?? profiles[0]?.name ?? "";
  const defaultRecipe = settings?.writing.format ?? "report";
  const options: RunOptions = {
    recipe: defaultRecipe,
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
  const languageInvalid = !isSearchLanguage(draft.searchLanguage.trim());
  const selected = profiles.find((p) => p.name === options.profile);
  const domainDefaults: DomainLists = {
    allow: selected?.allow_domains ?? settings?.domains.allow ?? [],
    block: selected?.block_domains ?? settings?.domains.block ?? [],
  };
  const domains: DomainLists = { ...domainDefaults, ...draft.domains };

  async function start() {
    if (blank || busy || languageInvalid || !defaults || !writing) return;
    const invalid = invalidDomain(domains);
    if (invalid) {
      setError(invalid);
      setOptionsOpen(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.createRun(
        runRequest(
          draft.query.trim(),
          options,
          writing,
          defaults,
          saved ?? defaults,
          values,
          overriddenDomains(domains, domainDefaults),
          draft.searchLanguage,
        ),
        draft.files,
      );
      setDraft(() => EMPTY_DRAFT);
      follow(created.run_id);
      go({ screen: "live", runId: created.run_id });
    } catch (e) {
      setError(startError(e));
      setBusy(false);
    }
  }

  /** A list equal to its default is no override, so it follows later default changes. */
  function setDomains(kind: DomainKind, list: string[] | null) {
    setDraft((d) => {
      const { [kind]: _, ...rest } = d.domains;
      const same = list === null || sameList(list, domainDefaults[kind]);
      return { ...d, domains: same ? rest : { ...rest, [kind]: list } };
    });
    if (error?.field === kind) setError(null);
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
  function editResearch(field: keyof ResearchValues, value: TokenBudget) {
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

  /** A Recipe equal to the default format is no override, so it follows later default changes. */
  function setOption<K extends keyof RunOptions>(key: K, value: RunOptions[K]) {
    setDraft((d) => {
      const { [key]: _, ...rest } = d.options;
      const same = key === "recipe" && value === defaultRecipe;
      return { ...d, options: same ? rest : { ...rest, [key]: value } };
    });
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
              disabled={blank || busy || languageInvalid}
              onClick={() => void start()}
            >
              <Play aria-hidden="true" />
              Run research
            </button>
          </div>
          {error && (
            <div role="alert" className={css.error}>
              <WarningCircle aria-hidden="true" className={css.errorIcon} />
              <div className={css.errorText}>
                <div className={css.errorTitle}>Couldn’t start the run</div>
                <div className={css.errorMessage}>{error.message}</div>
                {error.field && (
                  <button
                    type="button"
                    className={`btn btn-ghost ${css.fix}`}
                    onClick={() => {
                      setOptionsOpen(true);
                      setFocusField(error.field ?? null);
                    }}
                  >
                    Fix in Options
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
        <Attachments files={draft.files} onChange={(files) => setDraft((d) => ({ ...d, files }))} />
        {defaults && writing && values && (
          <OptionsPanel
            open={optionsOpen}
            onOpen={setOptionsOpen}
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
              gapEffective: effectiveGapContext(profile),
              wordsSet: options.depth === "custom" || presetOf(options.depth)?.values.words != null,
              onPick: pickDepth,
              onEdit: editResearch,
            }}
            onOption={setOption}
            writing={writing}
            defaults={defaults}
            onWriting={setWriting}
            onResetWriting={() => setDraft((d) => ({ ...d, writing: {} }))}
            domains={{
              lists: domains,
              defaults: domainDefaults,
              invalid: error?.field && error.entry ? { [error.field]: error.entry } : {},
              onChange: setDomains,
            }}
            searchLanguage={draft.searchLanguage}
            onSearchLanguage={(searchLanguage) => setDraft((d) => ({ ...d, searchLanguage }))}
          />
        )}
      </div>
    </div>
  );
}

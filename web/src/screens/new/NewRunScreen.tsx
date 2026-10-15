// New run: the question, attachments, and options; starts the run and opens it on Live run.
import {
  ArrowUUpLeft,
  CircleNotch,
  MagnifyingGlass,
  Play,
  Sparkle,
  TreeStructure,
  WarningCircle,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import type {
  DepthInfo,
  DomainLists,
  ProfileInfo,
  ProviderEntry,
  ResearchValues,
  RunCreate,
  RunKind,
  RunSummary,
  ServerSettings,
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
import { HelpTip } from "../../components/HelpTip";
import type { WritingField } from "../../components/WritingOptionsForm";
import { catalogRequest, structureRow } from "../../run/catalog";
import {
  CUSTOM_DESCRIPTION,
  type Depth,
  loadCustom,
  researchOf,
  saveCustom,
} from "../../run/depth";
import { depthDescription, type PresetKind } from "../../run/presets";
import {
  changedCount,
  type ProfileChoice,
  profileBase,
  profilePatch,
} from "../../run/profileValues";
import {
  draftFromRun,
  draftSignature,
  loadMarks,
  type Marks,
  pruneMarks,
  recentGroups,
  rowName,
  saveMarks,
} from "../../run/recent";
import { KIND_STEPS } from "../../run/thinking";
import { Attachments } from "./Attachments";
import { DeleteDialog } from "./DeleteDialog";
import css from "./NewRunScreen.module.css";
import {
  isSearchLanguage,
  OptionsPanel,
  overriddenDomains,
  overriddenFields,
  type ProfileView,
} from "./OptionsPanel";
import { RecentRuns, useWide } from "./RecentRuns";
import { depthGroups, profileGroups, profileIntro, SaveDialog } from "./SaveDialog";
import { focusStructureRow, StructurePanel } from "./StructurePanel";

/** The message of a failed save or delete, as the server wrote it. */
const failure = (error: unknown) => (error as Error).message;

/**
 * Why the server (or the entry check) refused the run; `field` names a domain row to fix, `row`
 * a Structure panel row. `title` replaces "Couldn’t start the run".
 */
type StartError = {
  message: string;
  field?: DomainKind;
  entry?: string;
  row?: string;
  title?: string;
};

const KIND_OPTIONS: {
  value: RunKind;
  label: string;
  title: string;
  Icon: typeof MagnifyingGlass;
}[] = [
  {
    value: "research",
    label: "Research",
    title: "Cited report or answer to a question",
    Icon: MagnifyingGlass,
  },
  {
    value: "catalog",
    label: "Catalog",
    title: "Structured records, one per entity, from a crawl",
    Icon: TreeStructure,
  },
];

const BRIEF_PLACEHOLDER =
  "e.g. Every public organization of the Peruvian state, from the three powers down to their attached bodies and offices, as structured records: name, acronym, type, parent, head and legal basis.";

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
  const row = structureRow(error.fields);
  if (row) return { message, row };
  const field = DOMAIN_KINDS.find((k) => `domains.${k}` in error.fields);
  if (!field) return { message };
  const entry = /'([^']*)'/.exec(error.fields[`domains.${field}`])?.[1];
  return { message, field, entry };
}

/**
 * The request for the form: the context recipe stops after select, and the report and answer
 * recipes send their `writing.format`; writing also holds overrides of
 * the depth-aware `defaults`. Custom sends its six values, and Length whenever it differs from
 * the saved default, since no preset sets it on the server. The profile's choice sends only
 * the changed blocks in `use` and the edited fields in `llm`.
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
  profile: ProfileChoice = { use: {}, edits: {} },
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
  return { ...request, ...profilePatch(profile, KIND_STEPS.research) };
}

export function NewRunScreen() {
  const api = useApi();
  const { draft, setDraft, follow, toast, isPhone } = useUi();
  const [settings, setSettings] = useState<ServerSettings | null>(null);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [depths, setDepths] = useState<DepthInfo[]>([]);
  const [error, setError] = useState<StartError | null>(null);
  const [busy, setBusy] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [entries, setEntries] = useState<ProviderEntry[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [focusField, setFocusField] = useState<DomainKind | null>(null);
  const [saving, setSaving] = useState<PresetKind | null>(null);
  const [deleting, setDeleting] = useState<{ kind: PresetKind; name: string } | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [marks, setMarks] = useState<Marks>(loadMarks);
  /** The run a row filled the form from, and the form's signature right after. */
  const [from, setFrom] = useState<{ id: string; sig: string } | null>(null);
  const wide = useWide() && !isPhone;
  const question = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!focusField || !(optionsOpen || draft.kind === "catalog")) return;
    const prefix = draft.kind === "catalog" ? "cd" : "nd";
    document.getElementById(domainInputId(prefix, focusField))?.focus();
    setFocusField(null);
  }, [focusField, optionsOpen, draft.kind]);

  useEffect(() => {
    question.current?.focus();
    api.getSettings().then(setSettings, () => {});
    api.listProfiles().then(setProfiles, () => {});
    api.listDepths().then(setDepths, () => {});
    api.listRuns().then(
      (listed) => {
        setRuns(listed);
        setMarks((m) => {
          const kept = pruneMarks(m, listed);
          saveMarks(kept);
          return kept;
        });
      },
      () => {},
    );
    api.listProviders().then(
      (report) => setEntries(report.entries),
      () => {},
    );
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
  const catalog = draft.kind === "catalog";
  const blank = !draft.query.trim();
  const blankBrief = !draft.brief.trim();
  const languageInvalid = !isSearchLanguage(draft.searchLanguage.trim());
  const selected = profiles.find((p) => p.name === options.profile);
  const domainDefaults: DomainLists = {
    allow: selected?.allow_domains ?? settings?.domains.allow ?? [],
    block: selected?.block_domains ?? settings?.domains.block ?? [],
  };
  const domains: DomainLists = { ...domainDefaults, ...draft.domains };
  const choice: ProfileChoice = { use: draft.use, edits: draft.profileEdits };
  /** The profile's Advanced values, shared by the research and catalog forms. */
  const profileView: ProfileView = {
    entries,
    choice,
    models,
    onChange: ({ use, edits }) => setDraft((d) => ({ ...d, use, profileEdits: edits })),
    actions: {
      onSaveTo: () => void saveProfileTo(),
      onSaveAs: () => setSaving("profile"),
      onDelete: () => setDeleting({ kind: "profile", name: options.profile }),
    },
  };
  const llmEntry = profileBase(selected, entries, draft.use).use.llm;

  useEffect(() => {
    if (!llmEntry) return;
    api.listModels(llmEntry).then(setModels, () => setModels([]));
  }, [api, llmEntry]);

  const groups = recentGroups(runs, marks.pins);
  const fromRun =
    from && draftSignature(draft) === from.sig ? runs.find((r) => r.run_id === from.id) : undefined;

  function changeMarks(next: Marks) {
    setMarks(next);
    saveMarks(next);
  }

  /** Fills the form from a run; Undo brings back a form that had a question or edits. */
  function fill(run: RunSummary) {
    const name = rowName(run, marks.names);
    const next = draftFromRun(run, name, { profiles, depths, saved });
    const previous = { draft, from };
    setDraft(() => next);
    setFrom({ id: run.run_id, sig: draftSignature(next) });
    setError(null);
    if (draftSignature(draft) === draftSignature(EMPTY_DRAFT)) return;
    const cut = name.length > 28 ? `${name.slice(0, 28)}…` : name;
    toast(`Filled from “${cut}”`, {
      undo: () => {
        setDraft(() => previous.draft);
        setFrom(previous.from);
      },
    });
  }

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
      const request = runRequest(
        draft.query.trim(),
        options,
        writing,
        defaults,
        saved ?? defaults,
        values,
        overriddenDomains(domains, domainDefaults),
        draft.searchLanguage,
        choice,
      );
      if (draft.reused.length) {
        const names = draft.reused.map((f) => f.name);
        request.reuse_attachments = { run_id: draft.reused[0].runId, names };
      }
      const created = await api.createRun(request, draft.files);
      setDraft(() => EMPTY_DRAFT);
      follow(created.run_id);
      go({ screen: "live", runId: created.run_id });
    } catch (e) {
      setError(startError(e));
      setBusy(false);
    }
  }

  /** Drafts the structure from the brief, the attachments, and the profile's choice. */
  async function draftStructure() {
    if (blankBrief || drafting) return;
    setDrafting(true);
    setError(null);
    try {
      const structure = await api.draftStructure(
        {
          brief: draft.brief.trim(),
          profile: options.profile,
          ...profilePatch(choice, KIND_STEPS.catalog),
        },
        draft.files,
      );
      setDraft((d) => ({ ...d, structure }));
    } catch (e) {
      setError({ message: (e as Error).message, title: "Couldn’t draft the structure" });
    } finally {
      setDrafting(false);
    }
  }

  /** Starts the catalog run with the Structure panel's values. */
  async function startCatalog() {
    const structure = draft.structure;
    if (!structure || blankBrief || busy || drafting || languageInvalid) return;
    const invalid = invalidDomain(domains);
    if (invalid) {
      setError(invalid);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const request = catalogRequest({
        brief: draft.brief,
        structure,
        profile: options.profile,
        domains: overriddenDomains(domains, domainDefaults),
        searchLanguage: draft.searchLanguage,
        choice,
      });
      if (draft.reused.length) {
        const names = draft.reused.map((f) => f.name);
        request.reuse_attachments = { run_id: draft.reused[0].runId, names };
      }
      const created = await api.createRun(request, draft.files);
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
      return { ...d, custom, customFrom: undefined, writing, options: { ...d.options, depth } };
    });
  }

  /** Selects a preset just saved; its Length is the one shown, so no Length override is left. */
  function selectSaved(depth: Depth) {
    setDraft((d) => {
      const { words: _, ...writing } = d.writing;
      return { ...d, customFrom: undefined, writing, options: { ...d.options, depth } };
    });
  }

  const reloadDepths = () => api.listDepths().then(setDepths);
  const reloadProfiles = () => api.listProfiles().then(setProfiles);
  const clearEdits = () => setDraft((d) => ({ ...d, use: {}, profileEdits: {} }));

  /** The depth values a save sends: the six values and the Length shown. */
  const savedDepth = () => values && writing && { ...values, words: writing.words };

  async function saveDepthTo(name: string) {
    const body = savedDepth();
    if (!body) return;
    try {
      await api.replaceDepth(name, { description: depthDescription(body), values: body });
    } catch (e) {
      toast(failure(e), { error: true });
      return;
    }
    await reloadDepths().catch(() => {});
    selectSaved(name);
    toast(`Saved depth “${name}”`);
  }

  async function saveDepthAs(name: string) {
    const body = savedDepth();
    if (!body) return;
    await api.saveDepth({ name, description: depthDescription(body), values: body });
    await reloadDepths().catch(() => {});
    selectSaved(name);
    setSaving(null);
    toast(`Saved depth “${name}”`);
  }

  async function saveProfileTo() {
    const name = options.profile;
    try {
      await api.updateProfile(name, profilePatch(choice));
    } catch (e) {
      toast(failure(e), { error: true });
      return;
    }
    await reloadProfiles().catch(() => {});
    clearEdits();
    toast(`Saved profile “${name}”`);
  }

  async function saveProfileAs(name: string, description: string) {
    const from = options.profile;
    await api.saveProfile({
      name,
      from,
      description: description || `Based on ${from}.`,
      ...profilePatch(choice),
    });
    await reloadProfiles().catch(() => {});
    setOption("profile", name);
    setSaving(null);
    toast(`Saved profile “${name}”`);
  }

  async function confirmDelete() {
    if (!deleting) return;
    const { kind, name } = deleting;
    setDeleting(null);
    try {
      if (kind === "depth") await api.deleteDepth(name);
      else await api.deleteProfile(name);
    } catch (e) {
      toast(failure(e), { error: true });
      return;
    }
    if (kind === "depth") {
      await reloadDepths().catch(() => {});
      if (options.depth === name) pickDepth("standard");
    } else {
      await reloadProfiles().catch(() => {});
      if (options.profile === name) setOption("profile", active);
    }
    toast(`Deleted ${kind} “${name}”`);
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
      customFrom: options.depth === "custom" ? d.customFrom : options.depth,
      options: { ...d.options, depth: "custom" },
    }));
  }

  /**
   * A Recipe equal to the default format is no override, so it follows later default changes.
   * Switching the profile drops the edits of its Advanced values.
   */
  function setOption<K extends keyof RunOptions>(key: K, value: RunOptions[K]) {
    setDraft((d) => {
      const { [key]: _, ...rest } = d.options;
      const same = key === "recipe" && value === defaultRecipe;
      const next = { ...d, options: same ? rest : { ...rest, [key]: value } };
      return key === "profile" ? { ...next, use: {}, profileEdits: {} } : next;
    });
  }

  /** Picks a named profile; dropped Advanced edits can be brought back with Undo. */
  function pickProfile(name: string) {
    const count = changedCount(choice);
    const previous = { profile: options.profile, use: draft.use, edits: draft.profileEdits };
    setOption("profile", name);
    if (!count) return;
    toast(`Dropped ${count} ${count === 1 ? "edit" : "edits"} to ${previous.profile}`, {
      undo: () =>
        setDraft((d) => ({
          ...d,
          options: { ...d.options, profile: previous.profile },
          use: previous.use,
          profileEdits: previous.edits,
        })),
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
    : [{ name: options.profile, source: "user", active: true, description: "" }];
  const depthNames = depths.map((info) => info.name);
  const depthSave = savedDepth();
  const recent = (
    <RecentRuns
      groups={groups}
      marks={marks}
      onMarks={changeMarks}
      current={fromRun?.run_id ?? null}
      onFill={fill}
      wide={wide}
      phone={isPhone}
    />
  );
  return (
    <div className={css.page}>
      <div className={css.layout} data-wide={wide}>
        <div className={css.inner}>
          <div>
            {catalog ? (
              <>
                <h1 className={css.h1}>New catalog run</h1>
                <p className={css.intro}>
                  wosarcher crawls out from seed records, extracts one structured record per node,
                  and returns them as a table.
                </p>
              </>
            ) : (
              <>
                <h1 className={css.h1}>New research run</h1>
                <p className={css.intro}>
                  wosarcher searches the web and your files, scores passages for relevance, and
                  writes a cited report.
                </p>
              </>
            )}
          </div>
          <div className="field">
            <div className={css.kindRow}>
              <div className={`seg ${css.kind}`} role="radiogroup" aria-label="Kind">
                {KIND_OPTIONS.map(({ value, label, title, Icon }) => (
                  <label key={value} className={`seg-opt ${css.kindOpt}`} title={title}>
                    <input
                      type="radio"
                      name="run-kind"
                      checked={draft.kind === value}
                      onChange={() => {
                        setDraft((d) => ({ ...d, kind: value }));
                        setError(null);
                      }}
                    />
                    <Icon aria-hidden="true" />
                    {label}
                  </label>
                ))}
              </div>
              <HelpTip help="kind" label="Kind" />
            </div>
            <div className={css.questionHead}>
              <label htmlFor="q">{catalog ? "Brief" : "Question"}</label>
              {!catalog && fromRun && (
                <span
                  className={`tag tag-neutral ${css.from}`}
                  title="The form matches this run. Edit anything to clear."
                >
                  <ArrowUUpLeft aria-hidden="true" className={css.fromIcon} />
                  <span className={css.fromName}>from: {rowName(fromRun, marks.names)}</span>
                </span>
              )}
            </div>
            <textarea
              id="q"
              ref={question}
              className={`input ${css.question}`}
              rows={6}
              value={catalog ? draft.brief : draft.query}
              placeholder={
                catalog
                  ? BRIEF_PLACEHOLDER
                  : "e.g. How do speculative decoding methods trade off acceptance rate against draft-model size on 12 GB GPUs?"
              }
              onChange={(e) => {
                const text = e.target.value;
                setDraft((d) => (catalog ? { ...d, brief: text } : { ...d, query: text }));
              }}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                  e.preventDefault();
                  void (catalog ? startCatalog() : start());
                }
              }}
            />
            <div className={css.actions}>
              <span className={css.hint}>
                <kbd>Ctrl</kbd>+<kbd>Enter</kbd>to run
              </span>
              {catalog ? (
                <div className={css.catalogActions}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={blankBrief || drafting}
                    aria-busy={drafting}
                    onClick={() => void draftStructure()}
                  >
                    {drafting ? (
                      <CircleNotch aria-hidden="true" className="spin" />
                    ) : (
                      <Sparkle aria-hidden="true" />
                    )}
                    {drafting ? "Drafting…" : "Draft structure"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={!draft.structure || blankBrief || drafting || busy || languageInvalid}
                    onClick={() => void startCatalog()}
                  >
                    <Play aria-hidden="true" />
                    Run catalog
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className={`btn btn-primary ${css.run}`}
                  disabled={blank || busy || languageInvalid}
                  onClick={() => void start()}
                >
                  <Play aria-hidden="true" />
                  Run research
                </button>
              )}
            </div>
            {error && (
              <div role="alert" className={css.error}>
                <WarningCircle aria-hidden="true" className={css.errorIcon} />
                <div className={css.errorText}>
                  <div className={css.errorTitle}>{error.title ?? "Couldn’t start the run"}</div>
                  <div className={css.errorMessage}>{error.message}</div>
                  {catalog && (error.row || error.field) && (
                    <button
                      type="button"
                      className={`btn btn-ghost ${css.fix}`}
                      onClick={() => {
                        if (error.row) focusStructureRow(error.row);
                        else setFocusField(error.field ?? null);
                      }}
                    >
                      Fix in Structure
                    </button>
                  )}
                  {!catalog && error.field && (
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
          {!wide && recent}
          <Attachments
            files={draft.files}
            reused={draft.reused}
            onChange={(files) => setDraft((d) => ({ ...d, files }))}
            onReused={(reused) => setDraft((d) => ({ ...d, reused }))}
          />
          {catalog &&
            (draft.structure ? (
              <StructurePanel
                structure={draft.structure}
                onChange={(structure) => setDraft((d) => ({ ...d, structure }))}
                domains={{
                  lists: domains,
                  defaults: domainDefaults,
                  invalid: error?.field && error.entry ? { [error.field]: error.entry } : {},
                  onChange: setDomains,
                }}
                profile={{
                  ...profileView,
                  profiles: profileList,
                  name: options.profile,
                  words: writing?.words ?? defaults?.words ?? 0,
                  onPick: pickProfile,
                }}
                searchLanguage={draft.searchLanguage}
                onSearchLanguage={(searchLanguage) => setDraft((d) => ({ ...d, searchLanguage }))}
                isPhone={isPhone}
              />
            ) : (
              <span className={css.structureNone}>
                Draft a structure from your brief to review its fields, seeds and limits before
                running.
              </span>
            ))}
          {!catalog && defaults && writing && values && (
            <OptionsPanel
              open={optionsOpen}
              onOpen={setOptionsOpen}
              options={options}
              profiles={profileList}
              depth={{
                presets: depths,
                customFrom: draft.customFrom,
                description:
                  options.depth === "custom"
                    ? CUSTOM_DESCRIPTION
                    : (presetOf(options.depth)?.description ?? ""),
                values,
                wordsSet:
                  options.depth === "custom" || presetOf(options.depth)?.values.words != null,
                onPick: pickDepth,
                onEdit: editResearch,
                actions: {
                  onSaveTo: (name) => void saveDepthTo(name),
                  onSaveAs: () => setSaving("depth"),
                  onDelete: (name) => setDeleting({ kind: "depth", name }),
                },
              }}
              profile={profileView}
              onOption={setOption}
              onProfile={pickProfile}
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
          {saving === "depth" && depthSave && (
            <SaveDialog
              kind="depth"
              existing={depthNames}
              groups={depthGroups(depthSave)}
              onSave={saveDepthAs}
              onClose={() => setSaving(null)}
            />
          )}
          {saving === "profile" && writing && (
            <SaveDialog
              kind="profile"
              existing={profiles.map((p) => p.name)}
              intro={profileIntro(options.profile, choice)}
              groups={profileGroups(selected, entries, choice, writing.words)}
              onSave={saveProfileAs}
              onClose={() => setSaving(null)}
            />
          )}
          {deleting && (
            <DeleteDialog
              kind={deleting.kind}
              name={deleting.name}
              switchNote={
                deleting.kind === "depth"
                  ? options.depth === deleting.name
                    ? " Depth switches to Standard."
                    : ""
                  : options.profile === deleting.name
                    ? ` New run switches to ${active}.`
                    : ""
              }
              onConfirm={() => void confirmDelete()}
              onClose={() => setDeleting(null)}
            />
          )}
        </div>
        {wide && <aside className={css.aside}>{recent}</aside>}
      </div>
    </div>
  );
}

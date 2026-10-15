// The collapsible Options panel of New run: depth, run options, and the writing options, which
// start from the saved defaults (Length from the depth) and mark per-run overrides.
import { ArrowCounterClockwise, CaretDown, CaretRight } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type {
  DepthInfo,
  DomainLists,
  ProfileInfo,
  ProviderEntry,
  ResearchValues,
  WritingOptions,
} from "../../api/types";
import type { RunOptions } from "../../app/context";
import { go } from "../../app/route";
import { type DomainKind, DomainRows, sameList } from "../../components/DomainRows";
import { HelpTip } from "../../components/HelpTip";
import { Seg } from "../../components/Seg";
import {
  describeValue,
  type WritingField,
  WritingOptionsForm,
} from "../../components/WritingOptionsForm";
import { type Depth, depthLabel } from "../../run/depth";
import { changedCount, type ProfileChoice } from "../../run/profileValues";
import { type DepthActions, DepthGroup } from "./DepthGroup";
import css from "./OptionsPanel.module.css";
import { type ProfileActions, ProfileAdvanced } from "./ProfileAdvanced";

/** The fields of `value` that differ from `defaults`. */
export function overriddenFields(
  value: WritingOptions,
  defaults: WritingOptions,
): Partial<WritingOptions> {
  const fields = Object.keys(value) as WritingField[];
  return Object.fromEntries(
    fields.filter((f) => String(value[f]) !== String(defaults[f])).map((f) => [f, value[f]]),
  );
}

/** The domain lists that differ from their defaults. */
export function overriddenDomains(lists: DomainLists, defaults: DomainLists): Partial<DomainLists> {
  return Object.fromEntries(
    (["allow", "block"] as const)
      .filter((k) => !sameList(lists[k], defaults[k]))
      .map((k) => [k, lists[k]]),
  );
}

const LANGUAGE_PATTERN = /^[a-z]{2,3}(-[A-Za-z]{2,4}){0,2}$/;

/** The server's search language rule: empty, `all`, `auto`, or a code such as `es-PE`. */
export function isSearchLanguage(value: string): boolean {
  return value === "" || value === "all" || value === "auto" || LANGUAGE_PATTERN.test(value);
}

/** The domain rows: lists, their defaults, and the entry each row marks invalid. */
export type DomainView = {
  lists: DomainLists;
  defaults: DomainLists;
  invalid: Partial<Record<DomainKind, string>>;
  onChange: (kind: DomainKind, list: string[] | null) => void;
};

/** What the Depth row shows; `wordsSet` is false when the depth leaves Length to Settings. */
export type DepthView = {
  /** Every preset from `GET /api/depths`. */
  presets: DepthInfo[];
  /** The preset Custom's values came from by an edit. */
  customFrom?: string;
  description: string;
  values: ResearchValues;
  wordsSet: boolean;
  onPick: (depth: Depth) => void;
  onEdit: (field: keyof ResearchValues, value: number) => void;
  actions: DepthActions;
};

/** The profile's Advanced values: every entry, the run's choice, and the llm's model IDs. */
export type ProfileView = {
  entries: ProviderEntry[];
  choice: ProfileChoice;
  models: string[];
  onChange: (choice: ProfileChoice) => void;
  actions: ProfileActions;
};

type Props = {
  open: boolean;
  onOpen: (open: boolean) => void;
  options: RunOptions;
  profiles: ProfileInfo[];
  depth: DepthView;
  profile: ProfileView;
  onOption: <K extends keyof RunOptions>(key: K, value: RunOptions[K]) => void;
  /** Picks a named profile; drops the Advanced edits of the current one. */
  onProfile: (name: string) => void;
  writing: WritingOptions;
  defaults: WritingOptions;
  onWriting: <F extends WritingField>(field: F, value: WritingOptions[F]) => void;
  onResetWriting: () => void;
  domains: DomainView;
  /** The search language as typed. */
  searchLanguage: string;
  onSearchLanguage: (value: string) => void;
};

export function OptionsPanel(props: Props) {
  const { open, onOpen, options, profiles, onOption, writing, defaults, depth, domains } = props;
  const writingOverridden = Object.keys(overriddenFields(writing, defaults)).length;
  const overridden =
    writingOverridden + Object.keys(overriddenDomains(domains.lists, domains.defaults)).length;
  const Caret = open ? CaretDown : CaretRight;
  const languageValid = isSearchLanguage(props.searchLanguage.trim());
  const selected = profiles.find((p) => p.name === options.profile);
  const label = depthLabel(options.depth);
  const rounds = options.sources === "files" ? 1 : depth.values.rounds;
  const edits = changedCount(props.profile.choice);
  const summary = [
    label,
    options.recipe,
    options.sources,
    edits ? `custom (${options.profile})` : options.profile,
    `${writing.words} words`,
    describeValue("tone", writing.tone),
  ].join(" · ");
  return (
    <div className={css.panel}>
      <button
        type="button"
        className={css.toggle}
        aria-expanded={open}
        onClick={() => onOpen(!open)}
      >
        <Caret className={css.caret} aria-hidden="true" />
        <span className={css.title}>Options</span>
        <span className={css.summary}>{summary}</span>
        {overridden > 0 && (
          <span className={`tag tag-outline ${css.count}`}>{overridden} overridden</span>
        )}
      </button>
      {open && (
        <div className={css.body}>
          <div className={css.group}>Run</div>
          <DepthGroup
            depth={options.depth}
            presets={depth.presets}
            customFrom={depth.customFrom}
            description={depth.description}
            values={depth.values}
            filesOnly={options.sources === "files"}
            onPick={depth.onPick}
            onEdit={depth.onEdit}
            actions={depth.actions}
          />
          <Row label="Recipe" help="recipe">
            <Seg
              label="Recipe"
              name="opt-recipe"
              value={options.recipe}
              options={[
                { value: "report", label: "report" },
                { value: "answer", label: "answer" },
                { value: "context", label: "context" },
              ]}
              onChange={(v) => onOption("recipe", v)}
            />
          </Row>
          <Row label="Sources" help="sources">
            <Seg
              label="Sources"
              name="opt-sources"
              value={options.sources}
              options={(["web", "files", "both"] as const).map((v) => ({ value: v, label: v }))}
              onChange={(v) => onOption("sources", v)}
            />
          </Row>
          <Row
            label="Profile"
            help="profile"
            htmlFor={profiles.length > SEGMENT_PROFILES ? "opt-profile" : undefined}
          >
            <div className={css.profileRow}>
              <div className={css.profileSelect}>
                <ProfileControl
                  profiles={profiles}
                  profile={options.profile}
                  edits={edits}
                  onPick={props.onProfile}
                />
                {edits > 0 && (
                  <div className={css.based}>
                    based on <strong>{options.profile}</strong> · {edits}{" "}
                    {edits === 1 ? "edit" : "edits"}
                  </div>
                )}
                {selected?.description && (
                  <div className={css.description}>{selected.description}</div>
                )}
              </div>
              <ProfileAdvanced
                profile={selected}
                entries={props.profile.entries}
                choice={props.profile.choice}
                models={props.profile.models}
                words={writing.words}
                rounds={rounds}
                onChange={props.profile.onChange}
                actions={props.profile.actions}
              />
            </div>
          </Row>
          <DomainRows
            idPrefix="nd"
            lists={domains.lists}
            bases={domains.defaults}
            invalid={domains.invalid}
            onChange={domains.onChange}
          />
          <Row label="Search language" help="search-language" htmlFor="opt-language">
            <input
              id="opt-language"
              className={`input ${css.profile}`}
              placeholder="Any language"
              value={props.searchLanguage}
              aria-invalid={!languageValid}
              onChange={(e) => props.onSearchLanguage(e.target.value)}
            />
            {languageValid ? (
              <div className={`${css.description} ${css.faint}`}>all, auto, es, es-PE…</div>
            ) : (
              <div className={`${css.description} ${css.danger}`}>
                Use all, auto, or a code such as es or es-PE.
              </div>
            )}
          </Row>
          <div className={css.writingHead}>
            <span className={css.group}>Writing</span>
            <span className={css.note}>Preselected from your defaults ·</span>
            <button
              type="button"
              className={`btn btn-ghost ${css.link}`}
              onClick={() => go({ screen: "settings" })}
            >
              edit defaults
            </button>
            {writingOverridden > 0 && (
              <button
                type="button"
                className={`btn btn-ghost ${css.link} ${css.resetAll}`}
                onClick={props.onResetWriting}
              >
                <ArrowCounterClockwise aria-hidden="true" />
                Reset all to defaults
              </button>
            )}
          </div>
          <WritingOptionsForm
            idPrefix="nw"
            value={writing}
            base={defaults}
            mark="overridden"
            baseLabel="default: "
            onChange={props.onWriting}
            wordsBaseText={depth.wordsSet ? `${label} default: ${defaults.words} words` : undefined}
            wordsHint={options.depth === "custom" ? undefined : `set by ${label}`}
          />
        </div>
      )}
    </div>
  );
}

/** Up to this many profiles show as segments; more use a select. */
const SEGMENT_PROFILES = 6;
const CUSTOM = "__custom";

type ProfileControlProps = {
  profiles: ProfileInfo[];
  profile: string;
  /** The Advanced edits of the profile; with any, `custom` is the selected choice. */
  edits: number;
  onPick: (name: string) => void;
};

function ProfileControl({ profiles, profile, edits, onPick }: ProfileControlProps) {
  const value = edits ? CUSTOM : profile;
  const pick = (name: string) => {
    if (name !== CUSTOM) onPick(name);
  };
  if (profiles.length <= SEGMENT_PROFILES)
    return (
      <Seg
        label="Profile"
        name="opt-profile"
        className={css.wrapSeg}
        value={value}
        options={[
          ...profiles.map((p) => ({ value: p.name, label: p.name })),
          ...(edits ? [{ value: CUSTOM, label: "custom" }] : []),
        ]}
        onChange={pick}
      />
    );
  return (
    <select
      id="opt-profile"
      className={`input ${css.profile}`}
      value={value}
      onChange={(e) => pick(e.target.value)}
    >
      {profiles.map((p) => (
        <option key={p.name} value={p.name}>
          {p.name}
        </option>
      ))}
      {edits > 0 && <option value={CUSTOM}>custom ({profile})</option>}
    </select>
  );
}

type RowProps = { label: string; help: string; htmlFor?: string; children: ReactNode };

function Row({ label, help, htmlFor, children }: RowProps) {
  const Label = htmlFor ? "label" : "span";
  return (
    <div className={css.row}>
      <div className={css.rowLabel}>
        <Label htmlFor={htmlFor}>{label}</Label>
        <HelpTip help={help} />
      </div>
      <div className={css.rowControl}>{children}</div>
    </div>
  );
}

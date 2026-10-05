// The collapsible Options panel of New run: depth, run options, and the writing options, which
// start from the saved defaults (Length from the depth) and mark per-run overrides.
import { ArrowCounterClockwise, CaretDown, CaretRight } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type {
  DomainLists,
  ProfileInfo,
  ResearchValues,
  TokenBudget,
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
import { DEPTH_LABELS, type Depth } from "../../run/depth";
import { DepthGroup } from "./DepthGroup";
import css from "./OptionsPanel.module.css";

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

/** The domain rows: lists, their defaults, and the entry each row marks invalid. */
export type DomainView = {
  lists: DomainLists;
  defaults: DomainLists;
  invalid: Partial<Record<DomainKind, string>>;
  onChange: (kind: DomainKind, list: string[] | null) => void;
};

/** What the Depth row shows; `wordsSet` is false when the depth leaves Length to Settings. */
export type DepthView = {
  depths: Depth[];
  description: string;
  values: ResearchValues;
  effective: number | null;
  gapEffective: number | null;
  queriesPerRound: number;
  wordsSet: boolean;
  onPick: (depth: Depth) => void;
  onEdit: (field: keyof ResearchValues, value: TokenBudget) => void;
};

type Props = {
  open: boolean;
  onOpen: (open: boolean) => void;
  options: RunOptions;
  profiles: ProfileInfo[];
  depth: DepthView;
  onOption: <K extends keyof RunOptions>(key: K, value: RunOptions[K]) => void;
  writing: WritingOptions;
  defaults: WritingOptions;
  onWriting: <F extends WritingField>(field: F, value: WritingOptions[F]) => void;
  onResetWriting: () => void;
  domains: DomainView;
};

export function OptionsPanel(props: Props) {
  const { open, onOpen, options, profiles, onOption, writing, defaults, depth, domains } = props;
  const writingOverridden = Object.keys(overriddenFields(writing, defaults)).length;
  const overridden =
    writingOverridden + Object.keys(overriddenDomains(domains.lists, domains.defaults)).length;
  const Caret = open ? CaretDown : CaretRight;
  const description = profiles.find((p) => p.name === options.profile)?.description;
  const label = DEPTH_LABELS[options.depth];
  const summary = [
    label,
    options.recipe,
    options.sources,
    options.profile,
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
            depths={depth.depths}
            description={depth.description}
            values={depth.values}
            effective={depth.effective}
            gapEffective={depth.gapEffective}
            queriesPerRound={depth.queriesPerRound}
            filesOnly={options.sources === "files"}
            onPick={depth.onPick}
            onEdit={depth.onEdit}
          />
          <Row label="Recipe" help="recipe">
            <Seg
              label="Recipe"
              name="opt-recipe"
              value={options.recipe}
              options={[
                { value: "report", label: "report" },
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
          <Row label="Profile" help="profile" htmlFor="opt-profile">
            <select
              id="opt-profile"
              className={`input ${css.profile}`}
              value={options.profile}
              onChange={(e) => onOption("profile", e.target.value)}
            >
              {profiles.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.source === "user" ? `${p.name}  (user profile)` : p.name}
                </option>
              ))}
            </select>
            {description && <div className={css.description}>{description}</div>}
          </Row>
          <DomainRows
            idPrefix="nd"
            lists={domains.lists}
            bases={domains.defaults}
            invalid={domains.invalid}
            onChange={domains.onChange}
          />
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

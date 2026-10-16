// The catalog form's Structure panel: record fields, child relation, seeds, leaf types, Expand
// by, Output, limits, domain rows, search language, and the estimate line (prototype scenario `new`
// with Catalog picked).
import { Check, Link, Plus, X } from "@phosphor-icons/react";
import { type KeyboardEvent, type ReactNode, useState } from "react";
import type { CatalogOutput, ExpandBy, Seed, Structure, StructureField } from "../../api/types";
import { DomainRows } from "../../components/DomainRows";
import { HelpTip } from "../../components/HelpTip";
import { Seg } from "../../components/Seg";
import {
  clampLimit,
  estimate,
  FIELD_TYPES,
  fieldName,
  LIMITS,
  limitsOf,
  typesOf,
} from "../../run/catalog";
import { type DomainView, isSearchLanguage } from "./OptionsPanel";
import css from "./StructurePanel.module.css";

/** The element "Fix in Structure" focuses: the first control of the named row. */
export function focusStructureRow(row: string) {
  const el = document.querySelector<HTMLElement>(
    `[data-row="${row}"] :is(input, select, button:not([data-help]))`,
  );
  el?.focus();
}

type Props = {
  structure: Structure;
  onChange: (structure: Structure) => void;
  domains: DomainView;
  isPhone: boolean;
};

export function StructurePanel(props: Props) {
  const { structure, onChange, isPhone } = props;
  const limits = limitsOf(structure);
  const types = typesOf(structure);
  const leaf = structure.leaf_types ?? [];
  const languageValid = isSearchLanguage((structure.language ?? "").trim());
  const recordLanguageValid = isSearchLanguage((structure.record_language ?? "").trim());
  const set = (patch: Partial<Structure>) => onChange({ ...structure, ...patch });
  const setField = (i: number, patch: Partial<StructureField>) =>
    set({ fields: structure.fields.map((f, j) => (j === i ? { ...f, ...patch } : f)) });

  return (
    <div className={css.wrap}>
      <div className={css.panel}>
        <div className={css.head}>
          <span className={css.group}>Structure</span>
          <span className={css.note}>Drafted from your brief · edit anything</span>
        </div>
        <Row label="Record fields" help="c-fields" id="c-fields-l" row="c-fields">
          {/* biome-ignore lint/a11y/useSemanticElements: the prototype's labelled group of controls */}
          <div role="group" aria-labelledby="c-fields-l" className={css.fields}>
            {!isPhone && (
              <div className={`${css.fieldRow} ${css.fieldHead}`}>
                <span>Name</span>
                <span>Type</span>
                <span>Required</span>
                <span className={css.volHead}>
                  Volatile
                  <HelpTip help="c-vol" />
                </span>
                <span />
              </div>
            )}
            {structure.fields.map((f, i) => {
              const label = f.name || `field ${i + 1}`;
              return (
                // biome-ignore lint/suspicious/noArrayIndexKey: fields are edited in place, by position
                <div key={i} className={css.fieldRow}>
                  <input
                    className={`input ${css.fieldName}`}
                    aria-label={`Field ${i + 1} name`}
                    value={f.name}
                    placeholder="field_name"
                    spellCheck={false}
                    autoComplete="off"
                    onChange={(e) => setField(i, { name: fieldName(e.target.value) })}
                  />
                  <select
                    className={`input ${css.fieldType}`}
                    aria-label={`Type of ${label}`}
                    value={f.type}
                    onChange={(e) => {
                      const type = e.target.value as StructureField["type"];
                      setField(
                        i,
                        type === "slug" || type === "ref" ? { type, example: "" } : { type },
                      );
                    }}
                  >
                    {FIELD_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <Switch
                    className={css.req}
                    on={!!f.required}
                    label={`Required: ${label}`}
                    text={isPhone ? "Required" : undefined}
                    onToggle={() => setField(i, { required: !f.required })}
                  />
                  <Switch
                    className={css.vol}
                    on={!!f.volatile}
                    label={`Volatile: ${label}`}
                    text={isPhone ? "Volatile" : undefined}
                    onToggle={() => setField(i, { volatile: !f.volatile })}
                  />
                  <button
                    type="button"
                    className={`btn btn-ghost btn-icon ${css.remove}`}
                    aria-label={`Remove field ${label}`}
                    onClick={() => set({ fields: structure.fields.filter((_, j) => j !== i) })}
                  >
                    <X aria-hidden="true" />
                  </button>
                  <input
                    className={`input ${css.fieldDesc}`}
                    aria-label={`Description of ${label}`}
                    value={f.description ?? ""}
                    placeholder="What this field holds"
                    maxLength={200}
                    autoComplete="off"
                    onChange={(e) => setField(i, { description: e.target.value })}
                  />
                  {f.example && (
                    <div className={css.fieldExample}>
                      <input
                        className={`input ${css.exampleChip}`}
                        readOnly
                        aria-label={`Example of ${label}`}
                        title={f.example}
                        value={f.example}
                      />
                      <HelpTip help="c-example" />
                    </div>
                  )}
                </div>
              );
            })}
            <button
              type="button"
              className={`btn btn-ghost ${css.add} ${css.addField}`}
              onClick={() =>
                set({
                  fields: [
                    ...structure.fields,
                    {
                      name: "",
                      type: "text",
                      required: false,
                      volatile: false,
                      description: "",
                      example: "",
                    },
                  ],
                })
              }
            >
              <Plus aria-hidden="true" />
              Add field
            </button>
          </div>
        </Row>
        <Row label="Child relation" help="c-rel" htmlFor="c-rel" row="c-rel">
          <input
            id="c-rel"
            className={`input ${css.relation}`}
            value={structure.relation}
            onChange={(e) => set({ relation: e.target.value })}
          />
        </Row>
        <Row label="Seeds" help="c-seeds" id="c-seeds-l" row="c-seeds">
          <Seeds
            seeds={structure.seeds}
            types={types}
            onChange={(seeds) => set({ seeds: seeds as Structure["seeds"] })}
          />
        </Row>
        <Row label="Leaf types" help="c-leaf" id="c-leaf-l" row="c-leaf">
          {/* biome-ignore lint/a11y/useSemanticElements: the prototype's labelled group of controls */}
          <div role="group" aria-labelledby="c-leaf-l" className={css.chips}>
            {types.map((t) => {
              const on = leaf.includes(t);
              return (
                <button
                  key={t}
                  type="button"
                  className={css.leaf}
                  aria-pressed={on}
                  onClick={() =>
                    set({ leaf_types: on ? leaf.filter((x) => x !== t) : [...leaf, t] })
                  }
                >
                  {on && <Check aria-hidden="true" />}
                  {t}
                </button>
              );
            })}
          </div>
        </Row>
        <Row label="Expand by" help="c-expand" id="c-exp-l" row="c-expand">
          <Seg<ExpandBy>
            label="Expand by"
            name="c-exp"
            value={structure.expand ?? "both"}
            onChange={(expand) => set({ expand })}
            options={[
              { value: "links", label: "Links" },
              { value: "search", label: "Search" },
              { value: "both", label: "Both" },
            ]}
          />
        </Row>
        <Row label="Output" help="c-output" id="c-out-l" row="c-output">
          <Seg<CatalogOutput>
            label="Output"
            name="c-out"
            value={structure.output ?? "table"}
            onChange={(output) => set({ output })}
            options={[
              { value: "table", label: "Table" },
              { value: "report", label: "Report" },
              { value: "both", label: "Both" },
            ]}
          />
        </Row>
        <Row label="Limits" help="c-limits" id="c-lim-l" row="c-limits">
          {/* biome-ignore lint/a11y/useSemanticElements: the prototype's labelled group of controls */}
          <div role="group" aria-labelledby="c-lim-l" className={css.limits}>
            {LIMITS.map((l) => (
              <label key={l.key} className={css.limit}>
                {l.label}
                <input
                  className={`input ${css.limitInput}`}
                  type="number"
                  min={l.min}
                  max={l.max}
                  value={Number.isNaN(limits[l.key]) ? "" : limits[l.key]}
                  onChange={(e) =>
                    set({
                      limits: {
                        ...limits,
                        [l.key]: clampLimit(l.key, Number.parseInt(e.target.value, 10)),
                      },
                    })
                  }
                />
              </label>
            ))}
          </div>
        </Row>
        <DomainRows
          idPrefix="cd"
          lists={props.domains.lists}
          bases={props.domains.defaults}
          invalid={props.domains.invalid}
          onChange={props.domains.onChange}
        />
        <Row label="Search language" help="c-lang" htmlFor="c-lang" row="c-lang">
          <input
            id="c-lang"
            className={`input ${css.language}`}
            placeholder="Any language"
            value={structure.language ?? ""}
            aria-invalid={!languageValid}
            onChange={(e) => set({ language: e.target.value })}
          />
          {languageValid ? (
            <div className={css.hint}>all, auto, es, es-PE…</div>
          ) : (
            <div className={css.danger}>Use all, auto, or a code such as es or es-PE.</div>
          )}
        </Row>
        <Row
          label="Record language"
          help="c-record-lang"
          htmlFor="c-record-lang"
          row="c-record-lang"
        >
          <input
            id="c-record-lang"
            className={`input ${css.language}`}
            placeholder="Sources’ language"
            value={structure.record_language ?? ""}
            aria-invalid={!recordLanguageValid}
            onChange={(e) => set({ record_language: e.target.value })}
          />
          {recordLanguageValid ? (
            <div className={css.hint}>es, en, es-PE…</div>
          ) : (
            <div className={css.danger}>Use a code such as es or es-PE.</div>
          )}
        </Row>
      </div>
      <span aria-live="polite" className={css.estimate}>
        {estimate(limits, structure.output ?? "table")}
      </span>
    </div>
  );
}

type RowProps = {
  label: string;
  help: string;
  row: string;
  /** The label's ID, for a group the label names. */
  id?: string;
  htmlFor?: string;
  children: ReactNode;
};

export function Row({ label, help, row, id, htmlFor, children }: RowProps) {
  return (
    <div className={css.row} data-row={row}>
      <div className={css.rowLabel}>
        {htmlFor ? <label htmlFor={htmlFor}>{label}</label> : <span id={id}>{label}</span>}
        <HelpTip help={help} />
      </div>
      <div className={css.rowControl}>{children}</div>
    </div>
  );
}

type SwitchProps = {
  on: boolean;
  label: string;
  text?: string;
  onToggle: () => void;
  className: string;
};

function Switch({ on, label, text, onToggle, className }: SwitchProps) {
  return (
    <div className={`${css.switchCell} ${className}`}>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label={label}
        className={css.switch}
        onClick={onToggle}
      >
        <span className={css.knob} />
      </button>
      {text && <span className={css.switchText}>{text}</span>}
    </div>
  );
}

type SeedsProps = {
  seeds: Seed[];
  types: string[];
  onChange: (seeds: Seed[]) => void;
};

function Seeds({ seeds, types, onChange }: SeedsProps) {
  const [adding, setAdding] = useState<{ name: string; type: string; url: string } | null>(null);
  const add = () => {
    if (!adding?.name.trim()) return;
    const url = adding.url.trim();
    onChange([...seeds, { name: adding.name.trim(), type: adding.type, url: url || null }]);
    setAdding(null);
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      add();
    } else if (e.key === "Escape") {
      e.stopPropagation();
      setAdding(null);
    }
  };
  return (
    // biome-ignore lint/a11y/useSemanticElements: the prototype's labelled group of controls
    <div role="group" aria-labelledby="c-seeds-l" className={css.seeds}>
      <div className={css.chips}>
        {seeds.map((s, i) => (
          <span
            // biome-ignore lint/suspicious/noArrayIndexKey: seeds can share a name
            key={i}
            className={css.seed}
            title={`${s.name} · ${s.type}${s.url ? ` · ${s.url}` : ""}`}
          >
            <span className={css.seedName}>{s.name}</span>
            <span className={css.seedType}>{s.type}</span>
            {s.url && (
              <a
                href={s.url}
                target="_blank"
                rel="noopener"
                aria-label={`Open ${s.name}`}
                className={css.seedLink}
              >
                <Link aria-hidden="true" />
              </a>
            )}
            <button
              type="button"
              className={css.chipX}
              aria-label={`Remove seed ${s.name}`}
              onClick={() => onChange(seeds.filter((_, j) => j !== i))}
            >
              <X aria-hidden="true" />
            </button>
          </span>
        ))}
      </div>
      {adding ? (
        <div className={css.seedAdd}>
          <input
            className={`input ${css.seedNameInput}`}
            aria-label="Seed name"
            placeholder="Name"
            value={adding.name}
            // biome-ignore lint/a11y/noAutofocus: the inputs open on "Add seed"
            autoFocus
            onChange={(e) => setAdding({ ...adding, name: e.target.value })}
            onKeyDown={onKey}
          />
          <select
            className={`input ${css.seedTypeInput}`}
            aria-label="Seed type"
            value={adding.type}
            onChange={(e) => setAdding({ ...adding, type: e.target.value })}
            onKeyDown={onKey}
          >
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            className={`input ${css.seedUrlInput}`}
            aria-label="Seed URL (optional)"
            placeholder="https://… (optional)"
            spellCheck={false}
            value={adding.url}
            onChange={(e) => setAdding({ ...adding, url: e.target.value })}
            onKeyDown={onKey}
          />
          <button
            type="button"
            className={`btn btn-secondary ${css.small}`}
            disabled={!adding.name.trim()}
            onClick={add}
          >
            Add
          </button>
          <button
            type="button"
            className={`btn btn-ghost ${css.small}`}
            onClick={() => setAdding(null)}
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          className={`btn btn-ghost ${css.add}`}
          onClick={() => setAdding({ name: "", type: types[0] ?? "", url: "" })}
        >
          <Plus aria-hidden="true" />
          Add seed
        </button>
      )}
    </div>
  );
}

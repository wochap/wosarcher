// The Allow domains and Block domains rows: a chips input per list, in the prototype's form grid.
// New run passes `bases` to mark lists that differ from their default; Settings passes none.
import { WarningCircle, X } from "@phosphor-icons/react";
import { type ClipboardEvent, type KeyboardEvent, type MouseEvent, useState } from "react";
import type { DomainLists } from "../api/types";
import css from "./DomainRows.module.css";
import { HelpTip } from "./HelpTip";
import { Tag } from "./Tag";

export type DomainKind = keyof DomainLists;
export const DOMAIN_KINDS: DomainKind[] = ["allow", "block"];

const LABELS: Record<DomainKind, string> = { allow: "Allow domains", block: "Block domains" };
const PLACEHOLDERS: Record<DomainKind, string> = { allow: "any domain", block: "none" };
const SEPARATOR = /[\s,]/;
/** The server's rule: lowercase letters, digits, and hyphens in two or more labels, no leading hyphen. */
const DOMAIN = /^[a-z0-9][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)+$/;

/** Typed or pasted text as entries: split on commas and white space, lowercased, trailing dot removed. */
export function domainEntries(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((entry) => entry.trim().toLowerCase().replace(/\.$/, ""))
    .filter(Boolean);
}

/** Whether the server accepts the entry; a leading `*.` or `.` is removed there too. */
export function isDomain(entry: string): boolean {
  return DOMAIN.test(entry.replace(/^\*?\./, ""));
}

export function sameList(a: string[], b: string[]): boolean {
  return a.join(",") === b.join(",");
}

/** The note under a row whose entry is not a domain. */
export function invalidNote(entry: string): string {
  return `Not a domain: ${entry}. Use the domain only, without a path.`;
}

/** The input of a row, for "Fix in Options". */
export function domainInputId(idPrefix: string, kind: DomainKind): string {
  return `${idPrefix}-${kind}`;
}

type Props = {
  idPrefix: string;
  lists: DomainLists;
  /** The defaults; a list that differs shows "overridden", "default: …", and Reset. */
  bases?: DomainLists;
  /** A list, or null to reset it to its base. */
  onChange: (kind: DomainKind, list: string[] | null) => void;
  /** The entry each row marks invalid. */
  invalid?: Partial<Record<DomainKind, string>>;
  /** A message under each row, such as a server error. */
  errors?: Partial<Record<DomainKind, string>>;
  spacious?: boolean;
};

export function DomainRows(props: Props) {
  return (
    <>
      {DOMAIN_KINDS.map((kind) => (
        <DomainRow key={kind} kind={kind} {...props} />
      ))}
    </>
  );
}

function DomainRow({
  kind,
  idPrefix,
  lists,
  bases,
  onChange,
  invalid,
  errors,
  spacious,
}: Props & { kind: DomainKind }) {
  const [draft, setDraft] = useState("");
  const list = lists[kind];
  const base = bases?.[kind];
  const changed = !!base && !sameList(list, base);
  const bad = invalid?.[kind] ?? "";
  const id = domainInputId(idPrefix, kind);
  const errId = `${id}-err`;
  const message = bad ? invalidNote(bad) : (errors?.[kind] ?? "");
  const label = LABELS[kind];

  function commit(text: string) {
    setDraft("");
    const added = domainEntries(text).filter((entry, n, all) => all.indexOf(entry) === n);
    const next = [...list, ...added.filter((entry) => !list.includes(entry))];
    if (next.length !== list.length) onChange(kind, next);
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (draft.trim()) commit(draft);
    } else if (e.key === "Backspace" && !draft && list.length) {
      onChange(kind, list.slice(0, -1));
    }
  }

  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData("text");
    if (text && SEPARATOR.test(text)) {
      e.preventDefault();
      commit(`${draft} ${text}`);
    }
  }

  function focus(e: MouseEvent<HTMLDivElement>) {
    const input = e.currentTarget.querySelector("input");
    if (input && e.target !== input) input.focus();
  }

  return (
    <div className={`${css.row} ${spacious ? css.spacious : ""}`}>
      <div className={css.head}>
        <div className={css.label}>
          <label htmlFor={id}>{label}</label>
          <HelpTip help={`d-${kind}`} label={label} />
        </div>
        {changed && base && (
          <>
            <div className={css.marks}>
              <span className={css.mark}>
                <Tag variant="outline" small>
                  overridden
                </Tag>
                <HelpTip help="d-over" />
              </span>
              <button
                type="button"
                className={`btn btn-ghost ${css.reset}`}
                onClick={() => onChange(kind, null)}
              >
                Reset
              </button>
            </div>
            <span className={css.base}>default: {base.length ? base.join(", ") : "none"}</span>
          </>
        )}
      </div>
      <div className={css.control}>
        {/* biome-ignore lint/a11y/noStaticElementInteractions: a click on the box focuses its input */}
        {/* biome-ignore lint/a11y/useKeyWithClickEvents: the input itself takes the keys */}
        <div className={`input ${css.box}`} data-invalid={!!bad} onClick={focus}>
          {list.map((entry) => (
            <span key={entry} className={css.chip} data-invalid={entry === bad}>
              <span className={css.chipText}>{entry}</span>
              <button
                type="button"
                className={css.remove}
                aria-label={`Remove ${entry}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onChange(
                    kind,
                    list.filter((x) => x !== entry),
                  );
                }}
              >
                <X aria-hidden="true" />
              </button>
            </span>
          ))}
          <input
            id={id}
            className={css.entry}
            value={draft}
            placeholder={list.length ? "" : PLACEHOLDERS[kind]}
            aria-invalid={!!bad}
            aria-describedby={message ? errId : undefined}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => {
              const value = e.target.value;
              if (SEPARATOR.test(value)) commit(value);
              else setDraft(value);
            }}
            onKeyDown={onKey}
            onBlur={() => {
              if (draft.trim()) commit(draft);
            }}
            onPaste={onPaste}
          />
        </div>
        {message && (
          <span id={errId} className={css.error}>
            <WarningCircle aria-hidden="true" className={css.errorIcon} />
            {message}
          </span>
        )}
        {kind === "allow" && (
          <span className={css.hint}>Suffix match: gob.pe also matches www.gob.pe.</span>
        )}
      </div>
    </div>
  );
}

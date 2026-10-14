// New run's Recent & pinned list: a column beside the form on wide windows, else a disclosure
// under the question. A row fills the form; its "…" menu renames, pins, or opens the run.
import {
  ArrowSquareOut,
  CaretDown,
  CaretRight,
  ClockCounterClockwise,
  DotsThree,
  type Icon,
  Paperclip,
  PencilSimple,
  PushPin,
  PushPinSlash,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { RunSummary } from "../../api/types";
import { go } from "../../app/route";
import { HelpTip } from "../../components/HelpTip";
import {
  type Marks,
  type RecentGroups,
  relativeDate,
  rename,
  rowName,
  rowSummary,
  togglePin,
} from "../../run/recent";
import css from "./RecentRuns.module.css";

const WIDE = "(min-width: 1200px)";
const wideMedia = () => (typeof window.matchMedia === "function" ? window.matchMedia(WIDE) : null);

/** True on windows at least 1200px wide. */
export function useWide(): boolean {
  const [wide, setWide] = useState(() => wideMedia()?.matches ?? false);
  useEffect(() => {
    const found = wideMedia();
    if (!found) return;
    const update = () => setWide(found.matches);
    found.addEventListener?.("change", update);
    return () => found.removeEventListener?.("change", update);
  }, []);
  return wide;
}

type Props = {
  groups: RecentGroups;
  marks: Marks;
  onMarks: (marks: Marks) => void;
  /** The run the form still matches. */
  current: string | null;
  onFill: (run: RunSummary) => void;
  wide: boolean;
  phone: boolean;
};

export function RecentRuns({ groups, marks, onMarks, current, onFill, wide, phone }: Props) {
  const [open, setOpen] = useState(false);
  const count = groups.pinned.length + groups.recent.length;
  const Caret = open ? CaretDown : CaretRight;
  const shown = wide || open;
  const rows = (runs: { run: RunSummary; count: number }[]) =>
    runs.map(({ run, count: n }, i) => (
      <Row
        key={run.run_id}
        run={run}
        count={n}
        marks={marks}
        onMarks={onMarks}
        current={current === run.run_id}
        onFill={() => {
          onFill(run);
          setOpen(false);
        }}
        menuUp={i >= runs.length - 2}
      />
    ));
  return (
    <section
      aria-labelledby="rp-h"
      className={wide ? css.column : css.disclosure}
      data-phone={phone}
    >
      {wide ? (
        <div className={css.head}>
          <h2 id="rp-h" className={css.title}>
            Recent &amp; pinned
          </h2>
          <HelpTip help="recent" />
          <span className={css.count}>{count}</span>
        </div>
      ) : (
        <div className={css.bar}>
          <button
            type="button"
            className={css.toggle}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Caret className={css.caret} aria-hidden="true" />
            <span id="rp-h" className={css.toggleTitle}>
              Recent &amp; pinned
            </span>
            <span className={css.toggleCount}>· {count}</span>
          </button>
          <HelpTip help="recent" />
        </div>
      )}
      {shown && (
        <div className={css.body}>
          {count === 0 && (
            <div className={css.empty}>
              <ClockCounterClockwise className={css.emptyIcon} aria-hidden="true" />
              <span className={css.emptyTitle}>No runs yet</span>
              <span className={css.emptyText}>
                Runs you start show up here. Pin the ones you repeat to keep them on top.
              </span>
            </div>
          )}
          {groups.pinned.length > 0 && (
            <Group title="Pinned">{rows(groups.pinned.map((run) => ({ run, count: 1 })))}</Group>
          )}
          {groups.recent.length > 0 && <Group title="Recent">{rows(groups.recent)}</Group>}
        </div>
      )}
    </section>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    // biome-ignore lint/a11y/useSemanticElements: the prototype's labelled group of rows
    <div role="group" aria-label={title} className={css.group}>
      <span className={css.groupTitle}>{title}</span>
      <ul className={css.list}>{children}</ul>
    </div>
  );
}

type RowProps = {
  run: RunSummary;
  count: number;
  marks: Marks;
  onMarks: (marks: Marks) => void;
  current: boolean;
  onFill: () => void;
  menuUp: boolean;
};

function Row({ run, count, marks, onMarks, current, onFill, menuUp }: RowProps) {
  const [menu, setMenu] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const name = rowName(run, marks.names);
  const files = run.attachments?.length ?? 0;
  const pinned = marks.pins.includes(run.run_id);
  const label = `Actions for ${name.length > 40 ? `${name.slice(0, 40)}…` : name}`;

  useEffect(() => {
    if (!menu) return;
    const close = (e: Event) => {
      if (
        e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)
      )
        setMenu(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [menu]);

  function commit(value: string) {
    if (editing === null) return;
    onMarks(rename(marks, run, value));
    setEditing(null);
  }

  const items: { label: string; icon: Icon; run: () => void }[] = [
    { label: "Rename", icon: PencilSimple, run: () => setEditing(name) },
    {
      label: pinned ? "Unpin" : "Pin",
      icon: pinned ? PushPinSlash : PushPin,
      run: () => onMarks(togglePin(marks, run.run_id)),
    },
    {
      label: "Open run",
      icon: ArrowSquareOut,
      run: () =>
        go(
          run.status === "done"
            ? { screen: "report", runId: run.run_id }
            : { screen: "live", runId: run.run_id },
        ),
    },
  ];

  return (
    <li className={css.row} data-current={current}>
      {editing !== null ? (
        <input
          className={`input ${css.rename}`}
          aria-label="Name"
          value={editing}
          placeholder={run.query}
          maxLength={120}
          // biome-ignore lint/a11y/noAutofocus: the input replaces the name the user chose to rename
          autoFocus
          onChange={(e) => setEditing(e.target.value)}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit(e.currentTarget.value);
            } else if (e.key === "Escape") {
              e.stopPropagation();
              setEditing(null);
            }
          }}
        />
      ) : (
        <button
          type="button"
          className={css.fill}
          title={run.query}
          aria-current={current || undefined}
          aria-label={`Fill the form from: ${name}`}
          onClick={onFill}
        >
          <span className={css.name}>{name}</span>
          <span className={css.summary}>{rowSummary(run)}</span>
          <span className={css.meta}>
            {files > 0 && (
              <span className={css.files}>
                <Paperclip aria-hidden="true" />
                {files} {files === 1 ? "file" : "files"}
              </span>
            )}
            <span>{relativeDate(run.created)}</span>
            {count > 1 && (
              <span title={`${count} runs with this question and options; showing the newest`}>
                ×{count}
              </span>
            )}
          </span>
        </button>
      )}
      <div className={css.menuBox} ref={box}>
        <button
          type="button"
          className={`btn btn-ghost btn-icon ${css.more}`}
          aria-label={label}
          aria-haspopup="menu"
          aria-expanded={menu}
          onClick={() => {
            setMenu(!menu);
            setEditing(null);
          }}
        >
          <DotsThree aria-hidden="true" />
        </button>
        {menu && (
          <div role="menu" aria-label={label} className={css.menu} data-up={menuUp}>
            {items.map((item) => (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                className={css.item}
                onClick={() => {
                  setMenu(false);
                  item.run();
                }}
              >
                <item.icon className={css.itemIcon} aria-hidden="true" />
                {item.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

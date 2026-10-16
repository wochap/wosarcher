// The Live run screen of a catalog run (scenario `live-catalog`): the 8-phase timeline, the
// Frontier tree, the Records cards, and Coverage.
import {
  ArrowsClockwise,
  CaretDown,
  CaretRight,
  Check,
  Circle,
  CircleNotch,
  Hourglass,
  type Icon,
  Link,
  StopCircle,
  Warning,
  XCircle,
} from "@phosphor-icons/react";
import { type ReactNode, useState } from "react";
import { HelpTip } from "../../components/HelpTip";
import {
  type CatalogLive,
  type CatalogPhase,
  type FrontierNode,
  fillPercents,
  frontierRows,
  liveRecords,
  nameField,
  nodesByType,
  nodeValues,
  phaseCards,
  shortField,
} from "../../run/catalog";
import type { AskState } from "../../run/questions";
import { fmtDuration } from "../../run/stageTimes";
import css from "./CatalogPanels.module.css";
import panel from "./Panel.module.css";
import timeline from "./PhaseTimeline.module.css";

const ICONS: Record<CatalogPhase["state"], Icon> = {
  pending: Circle,
  running: CircleNotch,
  done: Check,
  failed: XCircle,
  cancelled: StopCircle,
};

export function CatalogTimeline({
  live,
  now,
  write,
  ask,
}: {
  live: CatalogLive;
  now: number;
  /** The Write card's detail text; undefined for a run that writes no report. */
  write?: string;
  /** The run's questions: the Draft or Extract card that waits, and the answered notes. */
  ask?: AskState | null;
}) {
  return (
    <ol
      aria-label="Phases"
      className={`${timeline.timeline} ${css.timeline}`}
      data-phases={write === undefined ? 8 : 9}
    >
      {phaseCards(live, now, write).map((card) => {
        const asking = ask?.waiting?.stage === card.id ? ask.waiting : null;
        const note = asking ? undefined : ask?.stages[card.id];
        const Glyph = asking ? Hourglass : ICONS[card.state];
        const text = asking ? "waiting for you" : card.text;
        return (
          <li key={card.id} className={timeline.card} data-state={asking ? "asking" : card.state}>
            <div className={timeline.head}>
              <Glyph className={timeline.icon} aria-hidden="true" />
              <span className={timeline.label}>{card.label}</span>
              <HelpTip help={`cp-${card.id}`} label={card.label} />
            </div>
            <div className={timeline.text} title={text}>
              {text}
            </div>
            <div className={timeline.time}>
              <span data-tone={card.seconds === null ? "faint" : undefined}>
                {card.seconds === null ? "—" : fmtDuration(card.seconds)}
              </span>
            </div>
            {(asking || note) && (
              <div
                className={timeline.detail}
                data-tone={note?.warn ? "warn" : undefined}
                title={asking ? undefined : note?.text}
              >
                {asking ? `${asking.answered} of ${asking.total} answered` : note?.text}
              </div>
            )}
            {card.loop && (
              <div className={css.loop}>
                <ArrowsClockwise aria-hidden="true" />
                {card.loop}
              </div>
            )}
            <div className={timeline.track}>
              <div
                className={timeline.bar}
                style={{
                  width: `${asking ? Math.round((asking.answered / asking.total) * 100) : card.pct}%`,
                }}
              />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const DOT_LABEL: Record<FrontierNode["status"], string> = {
  discovered: "discovered",
  expanding: "expanding",
  extracted: "extracted",
  failed: "failed",
};

export function FrontierPanel({ live, className }: { live: CatalogLive; className?: string }) {
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
  const rows = frontierRows(live, closed);
  const short = shortField(live.fields);
  const toggle = (id: string) =>
    setClosed((c) => {
      const next = new Set(c);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <section aria-label="Frontier" className={`${panel.panel} ${className ?? ""}`}>
      <header className={panel.header}>
        <span className={css.titleHelp}>
          <h2 className={panel.title}>Frontier</h2>
          <HelpTip help="c-frontier" />
        </span>
        <span className={panel.summary}>{live.order.length} known</span>
      </header>
      {/* biome-ignore lint/a11y/noNoninteractiveElementToInteractiveRole: the prototype's tree of rows; carets are the controls */}
      <ul role="tree" aria-label="Frontier nodes" className={css.tree}>
        {rows.map(({ node, level, hasChildren }) => {
          const isClosed = closed.has(node.id);
          const acronym = short && node.record?.[short] != null ? String(node.record[short]) : "";
          const kids = node.children ?? 0;
          const kidsLong = kids === 1 ? "1 child" : `${kids} children`;
          return (
            // biome-ignore lint/a11y/useFocusableInteractive: rows are read, the caret buttons take focus
            <li
              key={node.id}
              role="treeitem"
              aria-level={level + 1}
              aria-expanded={hasChildren ? !isClosed : undefined}
              aria-label={`${node.name}${acronym ? ` (${acronym})` : ""}, ${node.type}, ${DOT_LABEL[node.status]}`}
              className={css.node}
              style={{ paddingLeft: 12 + level * 14 }}
            >
              {hasChildren ? (
                <button
                  type="button"
                  className={css.caret}
                  aria-label={`${isClosed ? "Expand" : "Collapse"} ${node.name}`}
                  onClick={() => toggle(node.id)}
                >
                  {isClosed ? <CaretRight aria-hidden="true" /> : <CaretDown aria-hidden="true" />}
                </button>
              ) : (
                <span aria-hidden="true" className={css.caretSpace} />
              )}
              <span
                aria-hidden="true"
                title={DOT_LABEL[node.status]}
                className={css.dot}
                data-status={node.status}
              />
              <span className={css.nodeMain}>
                <span className={css.nodeName} title={node.name}>
                  {node.name}
                </span>
                <span className={css.nodeMeta}>
                  {acronym && <span className={css.acronym}>{acronym}</span>}
                  <span className={`tag tag-neutral ${css.typeChip}`}>{node.type}</span>
                  {kids > 0 && (
                    <span className={css.kids} title={kidsLong}>
                      <span aria-hidden="true">{kids} ↳</span>
                      <span className="visually-hidden">{kidsLong}</span>
                    </span>
                  )}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** "12s ago", "3m ago". */
export function ago(ts: string, now: number): string {
  const s = Math.max(0, Math.round((now - Date.parse(ts)) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

const MONO_TYPES = new Set(["url", "ref", "date", "slug"]);

export function RecordsPanel({ live, now }: { live: CatalogLive; now: number }) {
  const records = liveRecords(live);
  const name = nameField(live.fields);
  const shown = live.fields.filter(
    (f) => f.name !== name && f.type !== "slug" && f.type !== "enum",
  );
  const times = new Map(live.records.map((r) => [r.id, r.ts]));
  return (
    <section aria-label="Records" className={panel.panel}>
      <header className={panel.header}>
        <h2 className={panel.title}>Records</h2>
        <span className={panel.summary}>{records.length} extracted · newest first</span>
      </header>
      <div className={panel.body}>
        {records.map((node) => {
          const values = nodeValues(node, live.fields);
          const title = String(node.record?.[name] ?? node.name);
          return (
            <article key={node.id} aria-label={`${title}, ${node.type}`} className={css.card}>
              <div className={css.cardHead}>
                <span className={css.cardName} title={title}>
                  {title}
                </span>
                <span className={css.cardMeta}>
                  <span className={`tag tag-neutral ${css.typeChip}`}>{node.type}</span>
                  <span className={css.ago}>{ago(times.get(node.id) ?? "", now)}</span>
                </span>
              </div>
              <dl className={css.grid}>
                {shown.map((f) => {
                  const value = values[f.name];
                  const missing = value == null || value === "";
                  const src = missing ? "" : node.sources[f.name];
                  const text = missing ? "—" : String(value);
                  return (
                    <div key={f.name} className={css.pair}>
                      <dt>{f.name}</dt>
                      <dd>
                        <span
                          title={text}
                          className={css.value}
                          data-missing={missing || undefined}
                          data-mono={MONO_TYPES.has(f.type) || undefined}
                        >
                          {text}
                        </span>
                        {src && (
                          <a
                            href={src}
                            target="_blank"
                            rel="noreferrer"
                            title={src}
                            aria-label={`Source for ${f.name} of ${title}`}
                            className={css.src}
                          >
                            <Link aria-hidden="true" />
                          </a>
                        )}
                      </dd>
                    </div>
                  );
                })}
              </dl>
              {node.flags.length > 0 && (
                <div className={css.flags}>
                  {node.flags.map((flag) => (
                    <span key={flag} className={css.flag}>
                      <Warning aria-hidden="true" />
                      {flag}
                    </span>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

/** Limits as bars: nodes known, deepest depth, pages fetched, each against its maximum. */
export function coverageLimits(live: CatalogLive) {
  const depth = live.order.reduce((d, id) => Math.max(d, live.nodes[id].depth), 0);
  const { max_nodes, max_depth, pages_per_node } = live.limits;
  return [
    { label: "Nodes", value: live.order.length, max: max_nodes },
    { label: "Depth", value: depth, max: max_depth },
    { label: "Pages", value: live.pages, max: max_nodes * pages_per_node },
  ].map((l) => ({ ...l, pct: l.max ? Math.min(100, Math.round((l.value / l.max) * 100)) : 0 }));
}

export function CoveragePanel({ live, action }: { live: CatalogLive; action?: ReactNode }) {
  const records = liveRecords(live).map((node) => nodeValues(node, live.fields));
  const fill = fillPercents(
    records,
    live.fields.map((f) => f.name),
  );
  const summary = live.done
    ? `${live.done.waves} ${live.done.waves === 1 ? "wave" : "waves"}`
    : live.wave
      ? `wave ${live.wave}`
      : "";
  return (
    <section aria-label="Coverage" className={panel.panel}>
      <header className={panel.header}>
        <span className={css.titleHelp}>
          <h2 className={panel.title}>Coverage</h2>
          <HelpTip help="c-coverage" />
        </span>
        <span className={panel.summary}>{summary}</span>
        {action}
      </header>
      <div className={`${panel.body} ${css.coverage}`}>
        <section aria-label="Limits" className={css.covSection}>
          <h3 className={css.h3}>Limits</h3>
          {coverageLimits(live).map((l) => (
            <div
              key={l.label}
              role="img"
              aria-label={`${l.label} ${l.value} of ${l.max}`}
              className={css.limit}
            >
              <div className={css.limitHead}>
                <span>{l.label}</span>
                <span className={css.limitValue}>
                  {l.value}
                  <span className={css.faint}> / {l.max}</span>
                </span>
              </div>
              <div className={css.track3}>
                <div className={css.barAccent} style={{ width: `${l.pct}%` }} />
              </div>
            </div>
          ))}
        </section>
        <section aria-label="Fill per field" className={css.covSection}>
          <div className={css.fillHead}>
            <h3 className={css.h3}>Fill per field</h3>
            <span className={css.lowest}>lowest first</span>
          </div>
          {fill.map((f) => (
            <div
              key={f.field}
              role="img"
              aria-label={`${f.field} filled in ${f.pct}% of records`}
              className={css.fillRow}
              data-low={f.pct < 50 || undefined}
            >
              <span className={css.fillName}>{f.field}</span>
              <div className={css.track4}>
                <div className={css.fillBar} style={{ width: `${f.pct}%` }} />
              </div>
              <span className={css.fillPct}>{f.pct}%</span>
            </div>
          ))}
        </section>
        <section aria-label="Nodes by type" className={css.covSection}>
          <h3 className={css.h3}>Nodes by type</h3>
          <ul className={css.types}>
            {nodesByType(live).map(([type, count]) => (
              <li key={type}>
                <span>{type}</span>
                <span className={css.typeCount}>{count}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </section>
  );
}

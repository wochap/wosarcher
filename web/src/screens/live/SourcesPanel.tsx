// Sources, newest first: found, fetched, cached (a fork's), failed, or not fetched (cancelled),
// plus the attached files with their size and the passages each source kept.
import {
  Check,
  FileText,
  GlobeSimple,
  type Icon,
  StopCircle,
  Warning,
  XCircle,
} from "@phosphor-icons/react";
import type { Context } from "../../api/generated";
import { fmtBytes } from "../../run/format";
import type { RunView, SourceView } from "../../run/reducer";
import type { FileRow } from "../../run/useRunData";
import panel from "./Panel.module.css";
import css from "./SourcesPanel.module.css";

type Row = {
  key: string;
  title: string;
  url: string;
  href?: string;
  state: string;
  tone: "muted" | "faint" | "danger";
  icon: Icon;
  kept: number;
  /** "round <k>" for a page a later research round fetched. */
  roundTag?: string;
};

const SKELETON = ["72%", "58%", "80%", "64%", "70%", "52%"];

function webRow(run: RunView, s: SourceView): Row {
  const base = {
    key: s.uri,
    title: s.title,
    url: s.uri.replace(/^https?:\/\//, ""),
    href: s.uri,
    kept: 0,
  };
  if (s.state === "failed")
    return { ...base, state: s.reason ?? "failed", tone: "danger", icon: XCircle };
  if (s.state === "fetched")
    return { ...base, state: s.cached ? "cached" : "fetched", tone: "muted", icon: Check };
  const cancelled = run.status === "cancelled";
  return {
    ...base,
    state: cancelled ? "not fetched" : "found",
    tone: "faint",
    icon: cancelled ? StopCircle : GlobeSimple,
  };
}

/** Kept passages per source id, from the context once selected, else from the scored events. */
function keptBySource(run: RunView, context: Context | null): Record<string, number> {
  const counts: Record<string, number> = {};
  const ids = context
    ? context.passages.map((p) => p.source_id)
    : run.passages.flatMap((q) => q.items.map((p) => p.source_id));
  for (const id of ids) counts[id] = (counts[id] ?? 0) + 1;
  return counts;
}

type Props = {
  run: RunView;
  files: FileRow[];
  context: Context | null;
  /** The run's `research.rounds`; round tags show only above 1. */
  rounds?: number;
  className?: string;
};

export function SourcesPanel({ run, files, context, rounds = 1, className }: Props) {
  const queued = run.status === "queued";
  const web = Object.values(run.sources).filter((s) => s.kind === "web");
  const selected = run.phases.select.state === "done" || run.phases.select.state === "reused";
  const kept = selected ? keptBySource(run, context) : {};
  const rows: Row[] = [
    ...files.map((f) => ({
      key: f.uri,
      title: f.title,
      url: f.uri,
      state: fmtBytes(f.size),
      tone: "muted" as const,
      icon: FileText,
      kept: kept[f.sourceId] ?? 0,
    })),
    ...web
      .map((s) => ({
        ...webRow(run, s),
        kept: kept[s.sourceId] ?? 0,
        roundTag: rounds > 1 && s.round > 1 ? `round ${s.round}` : undefined,
      }))
      .reverse(),
  ];
  const fetched = web.filter((s) => s.state === "fetched").length;
  const failed = web.filter((s) => s.state === "failed").length;
  return (
    <section aria-label="Sources" className={`${panel.panel} ${className ?? ""}`}>
      <header className={panel.header}>
        <h2 className={panel.title}>Sources</h2>
        <span className={panel.summary}>
          {queued ? "" : `${fetched} of ${web.length} fetched · ${files.length} files`}
        </span>
        {failed > 0 && (
          <span className={css.failed}>
            <Warning aria-hidden="true" />
            {failed} failed · run continues
          </span>
        )}
      </header>
      <div className={panel.body}>
        {queued &&
          SKELETON.map((width) => (
            <div key={width} className={css.skeleton} data-testid="skeleton">
              <div className={css.shimmer} style={{ width }} />
              <div className={css.line} />
            </div>
          ))}
        {!queued && !rows.length && (
          <div className={css.empty}>Sources appear as search returns results.</div>
        )}
        {rows.map((row) => {
          const Glyph = row.icon;
          return (
            <div key={row.key} className={css.row}>
              <Glyph className={css.icon} data-tone={row.tone} aria-hidden="true" />
              <div className={css.what}>
                {row.href ? (
                  <a className={css.title} href={row.href} target="_blank" rel="noreferrer">
                    {row.title}
                  </a>
                ) : (
                  <span className={css.title}>{row.title}</span>
                )}
                <div className={css.url}>{row.url}</div>
              </div>
              <div className={css.state}>
                <div data-tone={row.tone}>{row.state}</div>
                {row.kept > 0 && <div className={css.kept}>{row.kept} kept</div>}
                {row.roundTag && <div className={css.roundTag}>{row.roundTag}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// Scored passages, best first: display score with a 0 to 1 bar and the scorer's threshold
// marker, and one fate badge. The header holds the Cited | Kept | All filter (R cycles), the
// chunks › scored › kept › cited funnel, and the fate legend.
import {
  ArrowDown,
  CaretRight,
  Check,
  CircleDashed,
  Cpu,
  Funnel,
  Gauge,
  Hourglass,
  type Icon,
  MinusCircle,
  Quotes,
  Stack,
  StopCircle,
} from "@phosphor-icons/react";
import { useState } from "react";
import type { Context, SelectSkip } from "../../api/generated";
import type { WritingOptions } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
import { type FunnelConfig, type FunnelKey, funnelHelp } from "../../components/help";
import { domain, label } from "../../run/citations";
import { type Fate, fateOf, KEPT_FATES } from "../../run/fates";
import { isFallback } from "../../run/providers";
import type { RunView } from "../../run/reducer";
import type { PassageItem } from "../../run/scores";
import { unloading } from "./model";
import panel from "./Panel.module.css";
import css from "./PassagesPanel.module.css";

export type PassageFilter = "cited" | "kept" | "all";
export const FILTERS: PassageFilter[] = ["cited", "kept", "all"];
const FILTER_LABELS: Record<PassageFilter, string> = { cited: "Cited", kept: "Kept", all: "All" };

type Props = {
  run: RunView;
  context: Context | null;
  marker: WritingOptions["citation_marker"];
  /** Passages not kept by any query; null until loaded. */
  notKept: PassageItem[] | null;
  skips: SelectSkip[] | null;
  filter: PassageFilter;
  onFilter: (filter: PassageFilter) => void;
  /** The run's configured `score.provider`; another scorer in the results is a fallback. */
  configuredScorer?: string;
  /** The run's saved settings the funnel help quotes. */
  config?: Omit<FunnelConfig, "threshold">;
  /** When set, each card is a button that opens its passage; `opener` gets focus back on close. */
  onOpen?: (passage: PassageItem, opener: HTMLElement) => void;
  className?: string;
};

const fixed = (n: number) => n.toFixed(2);

/** Icon and label of each fate badge; `dim` cards are left out of the context. */
const FATES: Record<Fate, { icon: Icon; label: string; dim: boolean }> = {
  cited: { icon: Quotes, label: "cited", dim: false },
  kept: { icon: Check, label: "kept · selecting", dim: false },
  above: { icon: Hourglass, label: "≥", dim: false },
  srccap: { icon: Stack, label: "source cap", dim: true },
  budget: { icon: Gauge, label: "over budget", dim: true },
  qcap: { icon: Funnel, label: "query cap", dim: true },
  below: { icon: ArrowDown, label: "below", dim: true },
  pre: { icon: MinusCircle, label: "prefiltered", dim: true },
  pending: { icon: CircleDashed, label: "not scored yet", dim: true },
};

/** The scorer that produced the scores: the first query's other than `passthrough`. */
export function scorerTag(run: RunView, configured?: string): string | null {
  if (!run.passages.length) return null;
  const scorer = run.passages.find((q) => q.scorer !== "passthrough")?.scorer ?? "passthrough";
  return isFallback(configured, scorer) ? `${scorer} · fallback` : scorer;
}

/** The display threshold every scored query shares, else null. */
function sharedThreshold(run: RunView): number | null {
  const thresholds = new Set(run.passages.map((q) => q.threshold));
  const [only] = thresholds;
  return thresholds.size === 1 ? (only ?? null) : null;
}

function keptItems(run: RunView): PassageItem[] {
  return run.passages.flatMap((q) =>
    q.items.map((p) => ({
      ...p,
      queryId: q.queryId,
      scorer: q.scorer,
      threshold: q.threshold,
      kept: true,
    })),
  );
}

const finished = (run: RunView, phase: "chunk" | "score" | "select") =>
  run.phases[phase].state === "done" || run.phases[phase].state === "reused";

function emptyText(
  run: RunView,
  filter: PassageFilter,
  scoredAny: boolean,
): { text: string; icon: Icon; warn?: boolean } {
  const score = run.phases.score;
  if (run.status === "queued") return { text: "Waiting for the run to start.", icon: Hourglass };
  if (score.state === "waiting") {
    return {
      text: `Scorer is waiting for the GPU while the ${unloading(score.waitReason)} unloads.`,
      icon: Cpu,
      warn: true,
    };
  }
  if (run.status === "cancelled" && score.state !== "done") {
    return { text: "Cancelled before scoring.", icon: StopCircle };
  }
  if (scoredAny && filter === "cited" && !finished(run, "select")) {
    return {
      text: "Citations are assigned when Select finishes. Switch to All to watch scores arrive.",
      icon: Hourglass,
    };
  }
  if (scoredAny && filter === "kept" && !finished(run, "score")) {
    return {
      text: "Kept passages are known once scoring finishes. Switch to All to watch scores arrive.",
      icon: Hourglass,
    };
  }
  const chunks = run.phases.chunk.counters.count;
  const candidates = run.phases.prefilter.counters.count;
  const narrows =
    chunks && candidates
      ? ` The prefilter narrows ${chunks} chunks to ${candidates} for the scorer.`
      : "";
  return { text: `Passages appear as they are scored.${narrows}`, icon: Hourglass };
}

type Card = PassageItem & { fate: Fate };

type BadgeProps = {
  fate: Fate;
  threshold: number | null | undefined;
  /** The citation label, for `cited`. */
  mark?: string;
  /** The capping query, for `qcap`. */
  queryId?: string | null;
  className?: string;
};

/** One fate badge, as passage cards and the Source dialog show it. */
export function FateBadge({ fate, threshold, mark, queryId, className }: BadgeProps) {
  const { icon: FateIcon, label: fateLabel } = FATES[fate];
  const shown = threshold == null ? "threshold" : fixed(threshold);
  const text = fate === "above" ? `≥ ${shown}` : fate === "below" ? `below ${shown}` : fateLabel;
  return (
    <span className={`${css.badge} ${className ?? ""}`} data-fate={fate}>
      <FateIcon aria-hidden="true" className={css.badgeIcon} />
      <span className={css.badgeLabel}>{text}</span>
      {fate === "cited" && mark && <span className={css.mark}>{mark}</span>}
      {fate === "qcap" && queryId && <span className={css.query}>{queryId}</span>}
    </span>
  );
}

function PassageCard(props: {
  card: Card;
  mark: string;
  onOpen?: (p: PassageItem, opener: HTMLElement) => void;
}) {
  const { card: p, mark, onOpen } = props;
  const score = p.display == null ? "–" : fixed(p.display);
  return (
    <article
      className={css.passage}
      data-kept={p.kept}
      data-fate={p.fate}
      data-dim={FATES[p.fate].dim}
      data-open={!!onOpen || undefined}
    >
      {onOpen && (
        <button
          type="button"
          className={css.open}
          aria-label={`${score}, ${domain(p.uri)}. Open source`}
          onClick={(e) => onOpen(p, e.currentTarget)}
        />
      )}
      <div className={css.scoreLine}>
        <span className={css.score}>{score}</span>
        {p.display != null && (
          <div className={css.bar}>
            <div className={css.fill} style={{ width: `${p.display * 100}%` }} />
            {p.threshold != null && (
              <div
                className={css.threshold}
                style={{ left: `${p.threshold * 100}%` }}
                title={`threshold ${fixed(p.threshold)}`}
              />
            )}
          </div>
        )}
        <FateBadge fate={p.fate} threshold={p.threshold} mark={mark} queryId={p.queryId} />
      </div>
      <div className={css.where}>
        <span className={css.domain}>{domain(p.uri)}</span>
        {p.heading_path?.length ? ` · ${p.heading_path.join(" › ")}` : ""}
      </div>
      <p className={css.text}>{p.text}</p>
    </article>
  );
}

export function PassagesPanel(props: Props) {
  const { run, context, marker, notKept, skips, filter, onFilter, onOpen } = props;
  const [tailFor, setTailFor] = useState<string | null>(null);
  const showTail = tailFor === run.runId;
  const scoreDone = finished(run, "score");
  const selected = finished(run, "select");
  const kept = keptItems(run);
  const numbers = new Map(context?.passages.map((p) => [p.chunk_id, p.n]));
  const cards: Card[] = [...kept, ...(filter === "all" ? (notKept ?? []) : [])]
    .map((p) => ({ ...p, fate: fateOf(p, run, context, skips) }))
    .filter(
      (p) => filter === "all" || (filter === "cited" ? p.fate === "cited" : KEPT_FATES.has(p.fate)),
    )
    .sort((a, b) => (b.display ?? -1) - (a.display ?? -1));
  const listed = filter === "all" ? cards.filter((p) => p.fate !== "below") : cards;
  const tail = filter === "all" ? cards.filter((p) => p.fate === "below") : [];

  const scored = run.passages.reduce((n, q) => n + q.scored, 0);
  const cited = selected
    ? (context?.passages.length ?? kept.filter((p) => numbers.has(p.chunk_id)).length)
    : null;
  const counts: Record<PassageFilter, number | null> = {
    cited,
    kept: scoreDone ? kept.length : null,
    all: run.passages.length ? scored : null,
  };
  const threshold = sharedThreshold(run);
  const help = funnelHelp({ ...props.config, threshold });
  const funnel: [string, FunnelKey, number | null | undefined][] = [
    ["chunks", "f-chunks", finished(run, "chunk") ? run.phases.chunk.counters.count : null],
    ["scored", "f-scored", counts.all],
    ["kept", "f-kept", counts.kept],
    ["cited", "f-cited", cited],
  ];

  const tag = scorerTag(run, props.configuredScorer);
  const empty = cards.length ? null : emptyText(run, filter, run.passages.length > 0);
  const EmptyIcon = empty?.icon ?? Hourglass;
  const shown = tail.flatMap((p) => (p.display == null ? [] : [p.display]));
  const range = shown.length ? ` (${fixed(Math.min(...shown))}–${fixed(Math.max(...shown))})` : "";
  const below = threshold == null ? "the threshold" : fixed(threshold);
  const mark = (p: Card) => {
    const n = numbers.get(p.chunk_id);
    return n ? label(n, marker, context) : "";
  };

  return (
    <section aria-label="Passages" className={`${panel.panel} ${props.className ?? ""}`}>
      <header className={`${panel.header} ${css.header}`}>
        <div className={css.row}>
          <h2 className={panel.title}>Passages</h2>
          {tag && (
            <span className={css.scorer}>
              <span className={`tag tag-neutral ${css.tag}`}>{tag}</span>
              <HelpTip help="scorer" />
            </span>
          )}
          <div className={css.filters}>
            <div
              className={`seg ${css.seg}`}
              role="radiogroup"
              aria-label="Show passages (R cycles)"
            >
              {FILTERS.map((f) => (
                <label key={f} className={`seg-opt ${css.option}`}>
                  <input
                    type="radio"
                    name="passage-filter"
                    checked={filter === f}
                    onChange={() => onFilter(f)}
                  />
                  {FILTER_LABELS[f]}
                  <span className={css.count}>{counts[f] ?? ""}</span>
                </label>
              ))}
            </div>
            <kbd className={css.key} title="R cycles the filter">
              R
            </kbd>
          </div>
        </div>
        <fieldset className={css.funnel} aria-label="Pipeline">
          {funnel.map(([name, key, n], i) => (
            <span key={key} className={css.step}>
              {i > 0 && <CaretRight aria-hidden="true" className={css.caret} />}
              <HelpTip
                help={key}
                entry={help[key]}
                ariaLabel={`${n ?? "pending"} ${name}, help`}
                className={css.stepButton}
              >
                <span className={css.stepNumber} data-pending={n == null}>
                  {n ?? "–"}
                </span>
                <span className={css.stepLabel}>{name}</span>
              </HelpTip>
            </span>
          ))}
          <span className={css.fates}>
            Fates
            <HelpTip help="legend" entry={help.legend} />
          </span>
        </fieldset>
      </header>
      <div className={panel.body}>
        {empty && (
          <div className={panel.empty}>
            <EmptyIcon
              className={panel.emptyIcon}
              data-tone={empty.warn ? "warn" : undefined}
              aria-hidden="true"
            />
            <span>{empty.text}</span>
          </div>
        )}
        {listed.map((p) => (
          <PassageCard key={`${p.kept}-${p.chunk_id}`} card={p} mark={mark(p)} onOpen={onOpen} />
        ))}
        {tail.length > 0 && (
          <div className={css.tail}>
            <ArrowDown aria-hidden="true" className={css.tailIcon} />
            <span>
              {tail.length} more below {below} not listed{range}
            </span>
            <button
              type="button"
              className={`btn btn-ghost ${css.tailButton}`}
              aria-expanded={showTail}
              onClick={() => setTailFor(showTail ? null : run.runId)}
            >
              {showTail ? "Hide" : "Show"}
            </button>
          </div>
        )}
        {showTail &&
          tail.map((p) => (
            <PassageCard key={`${p.kept}-${p.chunk_id}`} card={p} mark="" onOpen={onOpen} />
          ))}
      </div>
    </section>
  );
}

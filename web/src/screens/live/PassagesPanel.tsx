// Scored passages, best first: display score with a 0 to 1 bar and the scorer's threshold
// marker, and the citation label once selected. Rejected ones show on demand (toggle or R).
import { Cpu, Hourglass, type Icon, StopCircle } from "@phosphor-icons/react";
import type { Context } from "../../api/generated";
import type { WritingOptions } from "../../api/types";
import { HelpTip } from "../../components/HelpTip";
import { domain, label } from "../../run/citations";
import type { RunView } from "../../run/reducer";
import type { PassageItem } from "../../run/scores";
import { unloading } from "./model";
import panel from "./Panel.module.css";
import css from "./PassagesPanel.module.css";

type Props = {
  run: RunView;
  context: Context | null;
  marker: WritingOptions["citation_marker"];
  rejected: PassageItem[] | null;
  showRejected: boolean;
  onToggle: () => void;
  /** The run's configured `score.provider`; another scorer in the results is a fallback. */
  configuredScorer?: string;
  className?: string;
};

const fixed = (n: number) => n.toFixed(2);

/** The scorer that produced the scores: the first query's other than `passthrough`. */
export function scorerTag(run: RunView, configured?: string): string | null {
  if (!run.passages.length) return null;
  const scorer = run.passages.find((q) => q.scorer !== "passthrough")?.scorer ?? "passthrough";
  return configured && scorer !== configured ? `${scorer} · fallback` : scorer;
}

/** " · ≥ 0.60" when every scored query shares one display threshold. */
function thresholdText(run: RunView): string {
  const thresholds = new Set(run.passages.map((q) => q.threshold));
  const [only] = thresholds;
  return thresholds.size === 1 && only != null ? ` · ≥ ${fixed(only)}` : "";
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

function emptyText(run: RunView, scoredAny: boolean): { text: string; icon: Icon; warn?: boolean } {
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
  if (scoredAny) {
    const threshold = run.passages.find((q) => q.threshold != null)?.threshold;
    const below = threshold == null ? "the threshold" : fixed(threshold);
    return {
      text: `No passages above ${below} yet. Press R to show rejected ones.`,
      icon: Hourglass,
    };
  }
  const chunks = run.phases.chunk.counters.count;
  const kept = run.phases.prefilter.counters.count;
  const narrows =
    chunks && kept ? ` Prefilter narrows ${chunks} chunks to ${kept} for the scorer.` : "";
  return { text: `Passages appear as they are scored.${narrows}`, icon: Hourglass };
}

export function PassagesPanel(props: Props) {
  const { run, context, marker, rejected, showRejected, onToggle } = props;
  const selected = run.phases.select.state === "done" || run.phases.select.state === "reused";
  const kept = keptItems(run);
  const items = [...kept, ...(showRejected ? (rejected ?? []) : [])];
  items.sort((a, b) => (b.display ?? -1) - (a.display ?? -1));
  const numbers = new Map(context?.passages.map((p) => [p.chunk_id, p.n]));
  const scored = run.passages.reduce((n, q) => n + q.scored, 0);
  const counters = run.phases.score.counters;
  let summary = "";
  if (selected) summary = `${kept.length} kept of ${scored} scored`;
  else if (run.passages.length)
    summary = `${counters.done ?? scored}/${counters.total ?? scored} scored`;
  if (summary) summary += thresholdText(run);
  const tag = scorerTag(run, props.configuredScorer);
  const empty = items.length ? null : emptyText(run, run.passages.length > 0);
  const EmptyIcon = empty?.icon ?? Hourglass;

  return (
    <section aria-label="Passages" className={`${panel.panel} ${props.className ?? ""}`}>
      <header className={`${panel.header} ${css.header}`}>
        <h2 className={panel.title}>Passages</h2>
        {tag && (
          <span className={css.scorer}>
            <span className={`tag tag-neutral ${css.tag}`}>{tag}</span>
            <HelpTip help="scorer" />
          </span>
        )}
        <span className={`${panel.summary} ${css.summary}`}>
          {summary}
          {summary && <HelpTip help="score" />}
        </span>
        <button
          type="button"
          className={css.toggle}
          aria-pressed={showRejected}
          title="Toggle rejected passages (R)"
          onClick={onToggle}
        >
          <span className={css.track}>
            <span className={css.knob} />
          </span>
          Rejected<span className={css.key}>R</span>
        </button>
        <HelpTip help="rejected" />
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
        {items.map((p) => {
          const n = numbers.get(p.chunk_id);
          let badge = "above threshold";
          if (!p.kept)
            badge = `rejected · below ${p.threshold == null ? "threshold" : fixed(p.threshold)}`;
          else if (selected && n) badge = label(n, marker, context);
          return (
            <article
              key={`${p.kept}-${p.chunk_id}`}
              className={css.passage}
              data-kept={p.kept}
              data-cited={p.kept && selected && !!n}
            >
              <div className={css.scoreLine}>
                <span className={css.score}>{p.display == null ? "–" : fixed(p.display)}</span>
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
                <span className={css.badge}>{badge}</span>
              </div>
              <div className={css.where}>
                <span className={css.domain}>{domain(p.uri)}</span>
                {p.heading_path?.length ? ` · ${p.heading_path.join(" › ")}` : ""}
              </div>
              <p className={css.text}>{p.text}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

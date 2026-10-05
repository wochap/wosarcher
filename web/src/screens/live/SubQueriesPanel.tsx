// The planner's sub-queries with their search state and result counts.
import { Check, CircleNotch, Clock, type Icon, Recycle, StopCircle } from "@phosphor-icons/react";
import { HelpTip } from "../../components/HelpTip";
import type { RunView, SubQuery } from "../../run/reducer";
import panel from "./Panel.module.css";
import css from "./SubQueriesPanel.module.css";

function state(run: RunView, q: SubQuery): { text: string; icon: Icon; spin?: boolean } {
  if (run.phases.search.state === "reused") return { text: "reused", icon: Recycle };
  if (q.done) return { text: `${q.results} results`, icon: Check };
  if (run.status === "cancelled") return { text: "cancelled", icon: StopCircle };
  if (run.phases.search.state === "running")
    return { text: "searching", icon: CircleNotch, spin: true };
  return { text: "queued", icon: Clock };
}

/** A query's text; `q0`, the planner's topic line, carries its label and help above the text. */
export function QueryText({
  id,
  text,
  className,
}: {
  id: string;
  text: string;
  className?: string;
}) {
  return (
    <span className={className}>
      {id === "q0" && (
        <span className={css.topic}>
          Topic line
          <HelpTip help="q0" />
        </span>
      )}
      {text}
    </span>
  );
}

export function SubQueriesPanel({ run, className }: { run: RunView; className?: string }) {
  const queued = run.status === "queued";
  const total = run.subQueries.length;
  const done = run.subQueries.filter((q) => q.done).length;
  return (
    <section aria-label="Sub-queries" className={`${panel.panel} ${className ?? ""}`}>
      <header className={panel.header}>
        <h2 className={panel.title}>Sub-queries</h2>
        <span className={panel.summary}>{queued || !total ? "" : `${done}/${total}`}</span>
      </header>
      {!total && (
        <div className={css.empty}>
          {queued ? "Waiting for the planner…" : "Planning sub-queries…"}
        </div>
      )}
      <ol className={css.list}>
        {run.subQueries.map((q) => {
          const s = state(run, q);
          const Glyph = s.icon;
          return (
            <li key={q.id} className={css.row}>
              <span className={css.n}>{q.id}</span>
              <QueryText id={q.id} text={q.text} className={css.text} />
              <span className={css.state}>
                <Glyph className={s.spin ? "spin" : undefined} aria-hidden="true" />
                {s.text}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

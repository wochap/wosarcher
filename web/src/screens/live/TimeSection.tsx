// Time per stage under the phase timeline, and the Report aside's version of it: a stacked bar
// of the queue, GPU waits, and stage times, the largest parts, and the full list.
import { CaretDown, CaretUp, Timer } from "@phosphor-icons/react";
import { useState } from "react";
import { HelpTip } from "../../components/HelpTip";
import type { PhaseId, RunView } from "../../run/reducer";
import { fmtDuration, type ListItem, type TimeBar, timeBar } from "../../run/stageTimes";
import { serverNow, shownPhases, skippedPhase } from "./PhaseTimeline";
import css from "./TimeSection.module.css";

type Props = {
  run: RunView;
  /** The run's creation time; the queue is `run.started` minus it. */
  created?: string;
  rounds: number;
  now: number;
};

function barOf({ run, created, rounds, now }: Props): TimeBar {
  const phases = shownPhases(rounds);
  return timeBar(run, phases, (id: PhaseId) => skippedPhase(id, run), created, serverNow(run, now));
}

function Bar({ bar }: { bar: TimeBar }) {
  return (
    <div role="img" aria-label={bar.aria} className={css.bar}>
      {bar.parts.map((part, n) => (
        <span
          // biome-ignore lint/suspicious/noArrayIndexKey: parts repeat kinds (one GPU wait per stage)
          key={n}
          title={part.title}
          data-kind={part.kind}
          className={css.part}
          style={{ flexGrow: bar.total ? Math.max((part.seconds / bar.total) * 1000, 0.01) : 1 }}
        />
      ))}
    </div>
  );
}

function AllStages({ items }: { items: ListItem[] }) {
  return (
    <ul className={css.all}>
      {items.map((item) => (
        <li key={`${item.kind}-${item.label}`} className={css.item} data-skipped={item.skipped}>
          <span className={css.itemHead}>
            <span aria-hidden="true" className={css.swatch} data-kind={item.kind} />
            <span className={css.itemLabel}>{item.label}</span>
            <span className={css.itemTime}>{item.time}</span>
            <span className={css.itemPct}>{item.pct}</span>
          </span>
          {item.note && <span className={css.itemNote}>{item.note}</span>}
        </li>
      ))}
    </ul>
  );
}

export function TimeSection(props: Props) {
  const [open, setOpen] = useState(false);
  const bar = barOf(props);
  if (!bar.parts.length) return null;
  const Caret = open ? CaretUp : CaretDown;
  return (
    <section aria-label="Time per stage" className={css.section}>
      <div className={css.row}>
        <span className={css.head}>
          <Timer aria-hidden="true" className={css.timer} />
          Time
          <HelpTip help="time" />
          <span className={css.total}>{fmtDuration(bar.total)}</span>
          {bar.running && <span>so far</span>}
        </span>
        <div className={css.barBox}>
          <Bar bar={bar} />
        </div>
        <div className={css.top}>
          {bar.top.map((part) => (
            <span key={part.label} className={css.topPart}>
              <span aria-hidden="true" className={css.swatch} data-kind={part.kind} />
              {part.label}
              <span className={css.topTime}>{part.time}</span>
              <span className={css.topPct}>{part.pct}</span>
            </span>
          ))}
          <button
            type="button"
            className={`btn btn-ghost ${css.toggle}`}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <Caret aria-hidden="true" />
            {open ? "Fewer" : "All stages"}
          </button>
        </div>
      </div>
      {open && (
        <div className={css.panel}>
          <AllStages items={bar.all} />
        </div>
      )}
    </section>
  );
}

/** The Report aside's time for a finished run: the total, the bar, and every stage. */
export function TimeAside(props: Omit<Props, "now">) {
  const ended = props.run.endedAt ? Date.parse(props.run.endedAt) : 0;
  const bar = barOf({ ...props, now: ended + (props.run.clockOffset ?? 0) });
  if (!bar.parts.length) return null;
  return (
    <section aria-label="Time per stage" className={css.aside}>
      <h2 className={css.asideTitle}>
        Time <span className={css.asideTotal}>{fmtDuration(bar.total)}</span>
        <HelpTip help="time" />
      </h2>
      <Bar bar={bar} />
      <AllStages items={bar.all} />
    </section>
  );
}

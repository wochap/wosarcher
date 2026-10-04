// The nine phase cards with progress text and a 3px bar; waiting for a device never looks like
// running.
import {
  Check,
  Circle,
  CircleNotch,
  Cpu,
  type Icon,
  Recycle,
  StopCircle,
  XCircle,
} from "@phosphor-icons/react";
import { HelpTip } from "../../components/HelpTip";
import { fmtK } from "../../run/format";
import { PHASES, type Phase, type PhaseId, type PhaseState, type RunView } from "../../run/reducer";
import { skippedByRecipe, stageLabel } from "./model";
import css from "./PhaseTimeline.module.css";

const ICONS: Record<PhaseState, Icon> = {
  pending: Circle,
  waiting: Cpu,
  running: CircleNotch,
  done: Check,
  reused: Recycle,
  failed: XCircle,
  cancelled: StopCircle,
};

const webSources = (run: RunView) => Object.values(run.sources).filter((s) => s.kind === "web");

/** Write tokens: the stage's count when done, else an estimate from the streamed text. */
export const writeTokens = (run: RunView) =>
  run.phases.write.counters.count ?? Math.round(run.report.length / 3.7);

function progress(id: PhaseId, phase: Phase, run: RunView): string {
  const c = phase.counters;
  const done = phase.state === "done";
  switch (id) {
    case "plan":
      return `${run.subQueries.length} sub-queries`;
    case "search":
      return done ? `${c.count} URLs found` : `found ${webSources(run).length}`;
    case "fetch": {
      const web = webSources(run);
      const ok =
        c.done !== undefined
          ? c.done - (c.failed ?? 0)
          : web.filter((s) => s.state === "fetched").length;
      const failed = c.failed ?? web.filter((s) => s.state === "failed").length;
      return `fetched ${ok}/${c.total ?? web.length}${failed ? ` · ${failed} failed` : ""}`;
    }
    case "load":
      return done
        ? `loaded ${c.count}/${c.count} files`
        : `loaded ${c.done ?? 0}/${c.total ?? 0} files`;
    case "chunk":
      return `${c.count ?? c.done ?? 0} chunks`;
    case "prefilter":
      return done
        ? `${c.count} of ${run.phases.chunk.counters.count ?? c.total ?? 0} kept`
        : `${c.done ?? 0}/${c.total ?? 0} embedded`;
    case "score":
      return done ? `${c.count} scored` : `scored ${c.done ?? 0}/${c.total ?? 0}`;
    case "select":
      return done ? `${c.count} selected` : "selecting";
    case "write":
      return `${fmtK(writeTokens(run))} tokens`;
  }
}

export type PhaseCard = { id: PhaseId; state: PhaseState; text: string; pct: number };

export function phaseCard(id: PhaseId, run: RunView): PhaseCard {
  const phase = run.phases[id];
  if (phase.state === "done" && phase.skipped)
    return { id, state: "done", text: "skipped", pct: 100 };
  if (phase.state === "pending" && skippedByRecipe(run, id)) {
    return { id, state: "done", text: "skipped", pct: 100 };
  }
  const { done, total } = phase.counters;
  const ratio = total ? Math.round((Math.min(done ?? 0, total) / total) * 100) : 0;
  switch (phase.state) {
    case "pending":
      return { id, state: "pending", text: "pending", pct: 0 };
    case "waiting":
      return { id, state: "waiting", text: `waiting for GPU · ${phase.waitReason}`, pct: 0 };
    case "reused":
      return { id, state: "reused", text: `reused from ${phase.copiedFrom}`, pct: 100 };
    case "failed":
      return { id, state: "failed", text: (phase.error ?? "failed").split("\n")[0], pct: ratio };
    case "cancelled":
      return {
        id,
        state: "cancelled",
        text: `cancelled · ${progress(id, phase, run)}`,
        pct: ratio,
      };
    case "done":
      return { id, state: "done", text: progress(id, phase, run), pct: 100 };
    case "running":
      return { id, state: "running", text: progress(id, phase, run), pct: ratio };
  }
}

export function PhaseTimeline({ run }: { run: RunView }) {
  return (
    <ol aria-label="Phases" className={css.timeline}>
      {PHASES.map((id) => {
        const card = phaseCard(id, run);
        const Glyph = ICONS[card.state];
        const label = stageLabel(id);
        const waiting = card.state === "waiting";
        return (
          <li key={id} className={css.card} data-state={card.state}>
            <div className={css.head}>
              <Glyph className={css.icon} aria-hidden="true" />
              <span className={css.label}>{label}</span>
              <HelpTip
                help={`${waiting ? "wait" : "ph"}-${id}`}
                label={waiting ? `${label}, waiting for GPU` : label}
              />
            </div>
            <div className={css.text}>{card.text}</div>
            <div className={css.track}>
              <div className={css.bar} style={{ width: `${card.pct}%` }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

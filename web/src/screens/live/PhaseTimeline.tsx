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
  Warning,
  XCircle,
} from "@phosphor-icons/react";
import { HelpTip } from "../../components/HelpTip";
import type { Help } from "../../components/help";
import { fmtK } from "../../run/format";
import { isFallback, methodOf, modelOf } from "../../run/providers";
import {
  LOOP_PHASES,
  PHASES,
  type Phase,
  type PhaseId,
  type PhaseState,
  type RunView,
} from "../../run/reducer";
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
    case "gap":
      return gapText(phase, run);
    case "select":
      return done ? `${c.count} selected` : "selecting";
    case "write":
      return `${fmtK(writeTokens(run))} tokens`;
  }
}

/** The Gap card: the round it reads, its last follow-up count, or how research ended. */
function gapText(phase: Phase, run: RunView): string {
  if (run.research) return `${run.research.ran} of ${run.research.planned} rounds`;
  if (phase.state === "running") return `reading round ${phase.round}`;
  const last = [...run.rounds].reverse().find((r) => typeof r.gap === "number");
  return last ? `${last.gap} follow-ups` : "pending";
}

/** A multi-round card's second line: the round it is in, or how many rounds it ran. */
export function roundDetail(id: PhaseId, run: RunView, planned: number): string {
  const phase = run.phases[id];
  if (planned < 2 || !LOOP_PHASES.includes(id) || phase.state === "pending" || phase.skipped)
    return "";
  if (id === "gap") return run.research ? run.research.reason : `after round ${phase.round}`;
  if (phase.state === "running" || phase.state === "waiting" || phase.state === "cancelled")
    return `round ${phase.round}/${planned}`;
  if (phase.state === "done" && !run.research && run.status === "running")
    return `round ${phase.round} done`;
  return phase.roundsDone ? `${phase.roundsDone} round${phase.roundsDone === 1 ? "" : "s"}` : "";
}

export type PhaseCard = { id: PhaseId; state: PhaseState; text: string; pct: number };

export function phaseCard(id: PhaseId, run: RunView): PhaseCard {
  const phase = run.phases[id];
  if (id === "gap" && phase.state === "pending")
    return { id, state: "pending", text: gapText(phase, run), pct: 0 };
  if (phase.state === "done" && phase.skipped && !(id === "gap" && run.research))
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

/** Phases whose card names the method that ran. */
const TAGGED: Partial<Record<PhaseId, true>> = {
  plan: true,
  prefilter: true,
  score: true,
  gap: true,
  write: true,
};
const TAG_STATES: PhaseState[] = ["running", "done", "reused", "failed", "cancelled"];

export type MethodTag = { text: string; fallback: boolean; help: Help };

/** The tag text for a provider string: the model for LLMs and embeddings, else the method. */
function tagLabel(id: PhaseId, provider: string): string {
  const method = methodOf(provider);
  const model = modelOf(provider);
  const llm = id === "plan" || id === "gap" || id === "write";
  if (model && (llm || method === "llm" || method === "embeddings")) return model;
  return method === "bm25" ? "BM25" : method;
}

const methodName = (method: string) => (method === "bm25" ? "keyword (BM25)" : method);

/** "embeddings (bge-small-en-v1.5)" or "rerank". */
function configuredName(provider: string): string {
  const model = modelOf(provider);
  return model ? `${methodOf(provider)} (${model})` : methodOf(provider);
}

/** The warning that explains a fallback, else the stage's error text. */
function fallbackReason(phase: Phase, configured: string): string | undefined {
  const method = methodOf(configured);
  const reason = phase.warnings.find((w) => w.includes("used ") || w.includes(method));
  return reason ?? phase.error?.split("\n")[0];
}

const sentence = (text: string) => (/[.!?]$/.test(text) ? text : `${text}.`);

function prefilterCounts(run: RunView, topK: number | undefined): string {
  const phase = run.phases.prefilter;
  const kept = phase.counters.count;
  const chunks = run.phases.chunk.counters.count;
  const parts: string[] = [];
  if (topK !== undefined) {
    const counts = kept !== undefined && chunks !== undefined ? `: ${kept} of ${chunks}` : "";
    parts.push(`Kept the top ${topK} chunks per sub-query${counts}.`);
  } else if (kept !== undefined && chunks !== undefined) parts.push(`Kept ${kept} of ${chunks}.`);
  if (run.passthrough.length)
    parts.push(`${run.passthrough.join(", ")} skipped ranking (small-input passthrough).`);
  return parts.join(" ");
}

function tagHelp(
  id: PhaseId,
  phase: Phase,
  ran: string,
  fallback: boolean,
  run: RunView,
  topK?: number,
): Help {
  const label = tagLabel(id, ran);
  const configured = phase.configuredProvider ?? ran;
  const reason = fallback ? fallbackReason(phase, configured) : undefined;
  const because = reason ? ` ${sentence(`Reason: ${reason}`)}` : "";
  const join = (...parts: string[]) => parts.filter(Boolean).join(" ");
  switch (id) {
    case "gap": {
      const on = phase.device ? ` Runs on ${phase.device}.` : "";
      return {
        title: `Gap · ${label}`,
        body: `Reads the best passages after each round and writes follow-up queries.${on}`,
      };
    }
    case "plan":
    case "write": {
      const role = id === "plan" ? "Planner" : "Writer";
      const on = phase.device ? `, on ${phase.device}.` : ".";
      return { title: `${role} · ${label}`, body: `The configured LLM${on}` };
    }
    case "prefilter": {
      const counts = prefilterCounts(run, topK);
      if (fallback)
        return {
          title: `Fallback · ${methodName(methodOf(ran))}`,
          body: join(
            `Configured: ${configuredName(configured)}.${because}`,
            `${label} ran instead.`,
            counts,
          ),
        };
      const model = modelOf(ran);
      return {
        title: `Prefilter · ${methodName(methodOf(ran))}`,
        body: join(`Ran ${model || label} as configured.`, counts),
      };
    }
    default:
      return {
        title: `Scorer · ${label}`,
        body: fallback
          ? join(`Configured: ${configuredName(configured)}.${because}`, `${label} ran instead.`)
          : `Ran ${label} as configured.`,
      };
  }
}

/** The method tag of a Plan, Prefilter, Score, or Write card; null when it has none. */
export function methodTag(id: PhaseId, run: RunView, topK?: number): MethodTag | null {
  const phase = run.phases[id];
  if (!TAGGED[id] || !TAG_STATES.includes(phase.state) || phase.skipped) return null;
  const ran =
    phase.state === "running"
      ? phase.configuredProvider
      : (phase.provider ?? phase.configuredProvider);
  if (!ran) return null;
  const fallback = phase.state !== "running" && isFallback(phase.configuredProvider, ran);
  const label = tagLabel(id, ran);
  return {
    text: fallback ? `${label} · fallback` : label,
    fallback,
    help: tagHelp(id, phase, ran, fallback, run, topK),
  };
}

/** The Prefilter card's second line; empty when it has none. */
export function prefilterDetail(run: RunView, topK?: number): string {
  const phase = run.phases.prefilter;
  if (topK === undefined || phase.skipped) return "";
  if (phase.state === "running") return `top ${topK} per sub-query`;
  if (phase.state !== "done" && phase.state !== "reused") return "";
  const passed = run.passthrough.length ? ` · ${run.passthrough.join(", ")} passthrough` : "";
  return `top ${topK}/sub-query${passed}`;
}

type Props = {
  run: RunView;
  /** The run's `prefilter.top_k`, from its request settings. */
  topK?: number;
  /** The run's `research.rounds`; the Gap card and round texts show only above 1. */
  rounds?: number;
};

export function PhaseTimeline({ run, topK, rounds = 1 }: Props) {
  const phases = rounds > 1 ? PHASES : PHASES.filter((id) => id !== "gap");
  return (
    <ol aria-label="Phases" className={css.timeline}>
      {phases.map((id) => {
        const card = phaseCard(id, run);
        const Glyph = ICONS[card.state];
        const label = stageLabel(id);
        const waiting = card.state === "waiting";
        const tag = methodTag(id, run, topK);
        const detail =
          roundDetail(id, run, rounds) || (id === "prefilter" ? prefilterDetail(run, topK) : "");
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
            {tag && (
              <HelpTip
                help={`m-${id}`}
                entry={tag.help}
                ariaLabel={`Method: ${tag.text}, details`}
                className={tag.fallback ? `${css.tag} ${css.fallback}` : css.tag}
              >
                {tag.fallback && <Warning className={css.tagIcon} aria-hidden="true" />}
                <span className={css.tagText}>{tag.text}</span>
              </HelpTip>
            )}
            <div className={css.text}>{card.text}</div>
            {detail && <div className={css.detail}>{detail}</div>}
            <div className={css.track}>
              <div className={css.bar} style={{ width: `${card.pct}%` }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

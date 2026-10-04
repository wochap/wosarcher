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

/** Phases whose card names the method that ran. */
const TAGGED: Partial<Record<PhaseId, true>> = {
  plan: true,
  prefilter: true,
  score: true,
  write: true,
};
const TAG_STATES: PhaseState[] = ["running", "done", "reused", "failed", "cancelled"];

export type MethodTag = { text: string; fallback: boolean; help: Help };

/** The tag text for a provider string: the model for LLMs and embeddings, else the method. */
function tagLabel(id: PhaseId, provider: string): string {
  const method = methodOf(provider);
  const model = modelOf(provider);
  if (model && (id === "plan" || id === "write" || method === "llm" || method === "embeddings"))
    return model;
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
};

export function PhaseTimeline({ run, topK }: Props) {
  return (
    <ol aria-label="Phases" className={css.timeline}>
      {PHASES.map((id) => {
        const card = phaseCard(id, run);
        const Glyph = ICONS[card.state];
        const label = stageLabel(id);
        const waiting = card.state === "waiting";
        const tag = methodTag(id, run, topK);
        const detail = id === "prefilter" ? prefilterDetail(run, topK) : "";
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

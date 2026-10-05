// Research rounds of a multi-round run: each round's queries, pages, and kept passages, the gap
// step between rounds, and why research stopped. Replaces the Sub-queries panel.
import {
  ArrowBendDownRight,
  Check,
  CircleDashed,
  CircleNotch,
  Clock,
  Files,
  type Icon,
  MinusCircle,
  PencilSlash,
  Prohibit,
  Stack,
  StopCircle,
  Warning,
} from "@phosphor-icons/react";
import { useState } from "react";
import { HelpTip } from "../../components/HelpTip";
import type { RoundQuery, RoundView, RunView, StopReason } from "../../run/reducer";
import panel from "./Panel.module.css";
import css from "./ResearchRoundsPanel.module.css";
import { QueryText } from "./SubQueriesPanel";

const COLLAPSE_ABOVE = 3;
const COLLAPSED = 2;

const DOING: Record<string, string> = {
  search: "searching",
  fetch: "fetching",
  chunk: "chunking",
  prefilter: "prefiltering",
  score: "scoring",
};

const STOP_ICONS: Record<StopReason, Icon> = {
  "no new sources": Prohibit,
  "page limit reached": Files,
  "no follow-ups": PencilSlash,
  "max rounds": Stack,
  "gap step failed": Warning,
};

type Look = { text: string; icon: Icon; spin?: boolean; tone?: "accent" };

function roundLook(round: RoundView): Look {
  if (round.state === "cancelled")
    return { text: `cancelled · ${round.newPages} new pages`, icon: StopCircle };
  if (round.state === "running") {
    const doing = DOING[round.stage ?? "search"] ?? "working";
    return {
      text: `${round.newPages} new pages · ${doing}`,
      icon: CircleNotch,
      spin: true,
      tone: "accent",
    };
  }
  if (!round.newPages)
    return { text: `0 new pages · ${round.knownPages} already fetched`, icon: MinusCircle };
  return { text: `${round.newPages} new pages · ${round.kept} kept`, icon: Check };
}

function queryLook(round: RoundView, query: RoundQuery): Look {
  if (query.searched) return { text: `${query.results} results`, icon: Check };
  if (round.state === "cancelled") return { text: "cancelled", icon: StopCircle };
  if (round.state === "running" && round.stage === "search")
    return { text: "searching", icon: CircleNotch, spin: true };
  return { text: "queued", icon: Clock };
}

function gapLine(round: RoundView, next: RoundView | undefined): Look | null {
  if (round.gap === "running")
    return {
      text: "Gap: reading the best passages so far…",
      icon: CircleNotch,
      spin: true,
      tone: "accent",
    };
  if (typeof round.gap !== "number") return null;
  const uncovered = round.uncovered.length ? ` · ${round.uncovered.length} uncovered` : "";
  if (round.gap > 0 && next)
    return {
      text: `Gap: ${round.gap} follow-up ${round.gap === 1 ? "query" : "queries"} for round ${round.round + 1}${uncovered}`,
      icon: ArrowBendDownRight,
    };
  if (round.gap === 0)
    return { text: `Gap: no usable follow-up query${uncovered}`, icon: PencilSlash };
  return null;
}

function Round({ round, next }: { round: RoundView; next: RoundView | undefined }) {
  const [toggled, setToggled] = useState<boolean | null>(null);
  const open = toggled ?? round.state === "running";
  const look = roundLook(round);
  const Glyph = look.icon;
  const long = round.queries.length > COLLAPSE_ABOVE;
  const queries = long && !open ? round.queries.slice(0, COLLAPSED) : round.queries;
  const gap = gapLine(round, next);
  const GapGlyph = gap?.icon;
  return (
    <li className={css.round}>
      <div className={css.head}>
        <Glyph
          className={`${css.icon} ${look.spin ? "spin" : ""}`}
          data-tone={look.tone}
          aria-hidden="true"
        />
        <span className={css.title}>Round {round.round}</span>
        <span className={css.kind}>{round.round === 1 ? "planner queries" : "gap follow-ups"}</span>
        <span className={css.status} data-tone={look.tone}>
          {look.text}
        </span>
      </div>
      {round.note && <div className={css.note}>{round.note}</div>}
      <ol className={css.queries}>
        {queries.map((query) => {
          const q = queryLook(round, query);
          const QueryGlyph = q.icon;
          return (
            <li key={query.id} className={css.query}>
              <span className={css.id}>{query.id}</span>
              <QueryText id={query.id} text={query.text} className={css.text} />
              <span className={css.queryState}>
                <QueryGlyph className={q.spin ? "spin" : undefined} aria-hidden="true" />
                {q.text}
              </span>
            </li>
          );
        })}
      </ol>
      {long && (
        <button
          type="button"
          className={`btn btn-ghost ${css.more}`}
          aria-expanded={open}
          onClick={() => setToggled(!open)}
        >
          {open ? "Show fewer" : `+${round.queries.length - COLLAPSED} more`}
        </button>
      )}
      {gap && GapGlyph && (
        <div className={css.gap} data-tone={gap.tone}>
          <GapGlyph className={gap.spin ? "spin" : undefined} aria-hidden="true" />
          {gap.text}
        </div>
      )}
    </li>
  );
}

function summary(run: RunView, started: RoundView[], planned: number): string {
  if (run.status === "cancelled") return "cancelled";
  if (run.research) return `${run.research.ran} of ${planned} rounds`;
  const running = started.find((r) => r.state === "running");
  if (running) return `round ${running.round}/${planned}`;
  const gap = started.find((r) => r.gap === "running");
  if (gap) return `gap after round ${gap.round}`;
  return run.status === "queued" ? "" : `up to ${planned} rounds`;
}

type Props = {
  run: RunView;
  /** The run's `research.rounds`. */
  planned: number;
  className?: string;
};

export function ResearchRoundsPanel({ run, planned, className }: Props) {
  const started = run.rounds.filter((r) => r.state !== "queued");
  const research = run.research;
  const total = research?.planned ?? planned;
  const latest = started[started.length - 1]?.round ?? 0;
  const remaining = total - latest;
  const StopGlyph = research ? STOP_ICONS[research.reason] : null;
  return (
    <section aria-label="Research rounds" className={`${panel.panel} ${className ?? ""}`}>
      <header className={panel.header}>
        <span className={css.heading}>
          <h2 className={panel.title}>Research rounds</h2>
          <HelpTip help="rounds" />
        </span>
        <span className={panel.summary}>{summary(run, started, total)}</span>
      </header>
      {!started.length && !research && (
        <div className={css.empty}>
          {run.status === "queued" ? "Waiting for the planner…" : "Planning round 1 queries…"}
        </div>
      )}
      <ol className={css.list}>
        {started.map((round) => (
          <Round
            key={round.round}
            round={round}
            next={started.find((r) => r.round === round.round + 1)}
          />
        ))}
        {research && StopGlyph && (
          <li className={css.stop}>
            <div className={css.stopHead}>
              <StopGlyph className={css.stopIcon} aria-hidden="true" />
              <span>
                {research.reason === "max rounds"
                  ? `All ${total} rounds ran · max rounds`
                  : `Stopped after round ${research.ran} of ${total} · ${research.reason}`}
              </span>
              <HelpTip help="r-stop" />
            </div>
            {research.reason !== "max rounds" && research.note && (
              <div className={css.stopNote}>{research.note}</div>
            )}
          </li>
        )}
        {!research && run.status === "running" && latest > 0 && remaining > 0 && (
          <li className={css.next}>
            <CircleDashed aria-hidden="true" />
            {remaining} more round{remaining > 1 ? "s" : ""} to go
          </li>
        )}
      </ol>
    </section>
  );
}

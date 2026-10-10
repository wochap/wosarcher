// Live run: the followed run's header, banner, phase timeline, panels, and footer; one panel
// at a time on phones. Nothing followed shows the empty state.
import { useCallback, useEffect, useState } from "react";
import type { RunDetail } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import { CitationTooltip, useCitation } from "../../run/CitationTooltip";
import { useRunData } from "../../run/useRunData";
import { CancelDialog } from "./CancelDialog";
import { EmptyLive } from "./EmptyLive";
import { LiveFooter } from "./LiveFooter";
import { LiveHeader } from "./LiveHeader";
import css from "./LiveScreen.module.css";
import { elapsedSeconds, settled, useNow } from "./model";
import { NotFound } from "./NotFound";
import { FILTERS, type PassageFilter, PassagesPanel } from "./PassagesPanel";
import { PhaseTimeline } from "./PhaseTimeline";
import { PhoneTabs } from "./PhoneTabs";
import { ReportPanel } from "./ReportPanel";
import { ResearchRoundsPanel } from "./ResearchRoundsPanel";
import { SourceDialog } from "./SourceDialog";
import { SourcesPanel } from "./SourcesPanel";
import { StatusBanner } from "./StatusBanner";
import { SubQueriesPanel } from "./SubQueriesPanel";

/** The run's configured `score.provider`, from the settings in its `request.json`. */
function configuredScorer(detail: RunDetail | null | undefined): string | undefined {
  const score = detail?.request?.settings.score as { provider?: string } | undefined;
  return score?.provider;
}

/** The run's `prefilter.top_k`, from the settings in its `request.json`. */
function prefilterTopK(detail: RunDetail | null | undefined): number | undefined {
  const prefilter = detail?.request?.settings.prefilter as { top_k?: number } | undefined;
  return prefilter?.top_k;
}

/** The run's resolved `research.rounds`, from the settings in its `request.json`; 1 when unset. */
export function plannedRounds(detail: RunDetail | null | undefined): number {
  const research = detail?.request?.settings.research as { rounds?: number } | undefined;
  return research?.rounds ?? detail?.rounds_planned ?? 1;
}

/** The run's caps the Passages funnel help quotes, from the settings in its `request.json`. */
function funnelConfig(detail: RunDetail | null | undefined) {
  const settings = detail?.request?.settings;
  const score = settings?.score as { top_k?: number } | undefined;
  const select = settings?.select as { max_chunks_per_source?: number } | undefined;
  return {
    prefilterTopK: prefilterTopK(detail),
    scoreTopK: score?.top_k,
    maxPerSource: select?.max_chunks_per_source,
  };
}

/** The open Source dialog: the source, the chunk selected on open, and the card to refocus. */
type OpenSource = { sourceId: string; chunkId: string; opener: HTMLElement };

const typing = (target: EventTarget | null) =>
  /^(INPUT|TEXTAREA|SELECT)$/.test((target as HTMLElement | null)?.tagName ?? "");

export function LiveScreen() {
  const api = useApi();
  const { followed, follow, live, isPhone, liveTab, setLiveTab, toast } = useUi();
  const data = useRunData(followed, live.view);
  const [filter, setFilter] = useState<PassageFilter>("kept");
  const [cancelling, setCancelling] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const keepRunning = useCallback(() => setConfirming(false), []);
  const [source, setSource] = useState<OpenSource | null>(null);
  const { cite, onCite, onLeave } = useCitation();
  const { loadNotKept } = data;

  const pickFilter = useCallback(
    (next: PassageFilter) => {
      if (next === "all") loadNotKept();
      setFilter(next);
    },
    [loadNotKept],
  );

  const closeSource = useCallback(() => {
    setSource((open) => {
      if (open?.opener.isConnected) setTimeout(() => open.opener.focus(), 0);
      return null;
    });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        source ||
        e.key.toLowerCase() !== "r" ||
        e.altKey ||
        e.ctrlKey ||
        e.metaKey ||
        typing(e.target)
      )
        return;
      pickFilter(FILTERS[(FILTERS.indexOf(filter) + 1) % FILTERS.length]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filter, pickFilter, source]);

  const view = data.view ?? live.view;
  const running = view?.status === "running";
  const now = useNow(running || view?.status === "queued");
  if (followed && (live.conn.notFound || data.notFound)) return <NotFound runId={followed} />;
  if (!followed || !view) return <EmptyLive />;

  const run = settled(view);
  const { detail, files, context, report } = data;
  const elapsed = elapsedSeconds(run, now);
  const attachments = detail?.request?.request.attachments?.length ?? files.length;
  const rounds = run.research?.planned ?? plannedRounds(detail);

  async function attempt(action: () => Promise<unknown>) {
    try {
      await action();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function cancel() {
    setCancelling(true);
    try {
      const outcome = await api.cancelRun(run.runId);
      // The run had already ended: show how, as the server tells it, instead of an error.
      if (outcome.kind === "not_active") {
        if (outcome.status) live.end({ status: outcome.status });
        live.refresh();
      }
    } finally {
      setCancelling(false);
    }
  }

  async function rerun() {
    const created = await api.rerunRun(run.runId);
    follow(created.run_id);
    go({ screen: "live", runId: created.run_id });
  }

  const tab = isPhone ? liveTab : null;
  const shows = (t: string) => tab === null || tab === t;
  const selected = run.phases.select.state === "done" || run.phases.select.state === "reused";
  const kept = run.passages.reduce((n, q) => n + q.items.length, 0);
  const writing = run.phases.write.state;
  const counts = {
    sources: run.status === "queued" ? "" : String(Object.keys(run.sources).length + files.length),
    passages: selected ? String(context?.passages.length ?? kept) : kept ? String(kept) : "",
    report: run.report ? (writing === "running" ? "…" : "✓") : "",
  };
  const marker = detail?.writing.citation_marker ?? "numeric";
  // While the run is active, a finished stage reloads the open Source dialog.
  const finishedStages = Object.values(run.phases).filter(
    (p) => p.state === "done" || p.state === "reused",
  ).length;

  return (
    <div className={css.live}>
      <LiveHeader
        run={run}
        detail={detail}
        files={attachments}
        isPhone={isPhone}
        cancelling={cancelling}
        onCancel={() =>
          detail?.origin === "cli" || detail?.origin === "api"
            ? setConfirming(true)
            : void attempt(cancel)
        }
        onOpenReport={() => go({ screen: "report", runId: run.runId })}
        onRerun={() => void attempt(rerun)}
      />
      {confirming && (detail?.origin === "cli" || detail?.origin === "api") && (
        <CancelDialog
          origin={detail.origin}
          tokenName={detail.token_name}
          onKeep={keepRunning}
          onCancel={() => {
            setConfirming(false);
            void attempt(cancel);
          }}
        />
      )}
      <StatusBanner
        run={run}
        conn={live.conn}
        elapsed={elapsed}
        now={now}
        rewriteOf={detail?.fork_from === "write" ? detail.parent_run_id : null}
      />
      {isPhone && <PhoneTabs tab={liveTab} onTab={setLiveTab} counts={counts} />}
      {shows("progress") && (
        <PhaseTimeline run={run} topK={prefilterTopK(detail)} rounds={rounds} />
      )}
      <div className={css.grid}>
        {(shows("progress") || shows("sources")) && (
          <div className={css.column}>
            {shows("progress") &&
              (rounds > 1 ? (
                <ResearchRoundsPanel run={run} planned={rounds} className={css.rounds} />
              ) : (
                <SubQueriesPanel run={run} className={css.subQueries} />
              ))}
            {shows("sources") && (
              <SourcesPanel
                run={run}
                files={files}
                context={context}
                rounds={rounds}
                className={css.sources}
              />
            )}
          </div>
        )}
        {shows("passages") && (
          <PassagesPanel
            run={run}
            context={context}
            marker={marker}
            notKept={data.notKept}
            skips={data.skips}
            filter={filter}
            onFilter={pickFilter}
            configuredScorer={configuredScorer(detail)}
            config={funnelConfig(detail)}
            onOpen={(p, opener) =>
              setSource({ sourceId: p.source_id, chunkId: p.chunk_id, opener })
            }
          />
        )}
        {shows("report") && (
          <ReportPanel
            run={run}
            report={report}
            context={context}
            writing={detail?.writing ?? null}
            isPhone={isPhone}
            onCite={onCite}
            onLeave={onLeave}
          />
        )}
      </div>
      <LiveFooter run={run} conn={live.conn} elapsed={elapsed} isPhone={isPhone} />
      <CitationTooltip cite={cite} context={context} marker={marker} />
      {source && (
        <SourceDialog
          key={`${run.runId}-${source.sourceId}`}
          runId={run.runId}
          sourceId={source.sourceId}
          chunkId={source.chunkId}
          reloadKey={running ? finishedStages : undefined}
          marker={marker}
          context={context}
          prefilterTopK={prefilterTopK(detail)}
          onClose={closeSource}
        />
      )}
    </div>
  );
}

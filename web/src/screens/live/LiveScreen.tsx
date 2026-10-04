// Live run: the followed run's header, banner, phase timeline, panels, and footer; one panel
// at a time on phones. Nothing followed shows the empty state.
import { useCallback, useEffect, useState } from "react";
import { useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import { CitationTooltip, useCitation } from "../../run/CitationTooltip";
import { useRunData } from "../../run/useRunData";
import { EmptyLive } from "./EmptyLive";
import { LiveFooter } from "./LiveFooter";
import { LiveHeader } from "./LiveHeader";
import css from "./LiveScreen.module.css";
import { elapsedSeconds, settled, useNow } from "./model";
import { NotFound } from "./NotFound";
import { PassagesPanel } from "./PassagesPanel";
import { PhaseTimeline } from "./PhaseTimeline";
import { PhoneTabs } from "./PhoneTabs";
import { ReportPanel } from "./ReportPanel";
import { SourcesPanel } from "./SourcesPanel";
import { StatusBanner } from "./StatusBanner";
import { SubQueriesPanel } from "./SubQueriesPanel";

const typing = (target: EventTarget | null) =>
  /^(INPUT|TEXTAREA|SELECT)$/.test((target as HTMLElement | null)?.tagName ?? "");

export function LiveScreen() {
  const api = useApi();
  const { followed, follow, live, isPhone, liveTab, setLiveTab, toast } = useUi();
  const data = useRunData(followed, live.view);
  const [showRejected, setShowRejected] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const { cite, onCite, onLeave } = useCitation();
  const { showRejected: loadRejected } = data;

  const toggleRejected = useCallback(() => {
    setShowRejected((on) => {
      if (!on) loadRejected();
      return !on;
    });
  }, [loadRejected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "r" || e.altKey || e.ctrlKey || e.metaKey || typing(e.target))
        return;
      toggleRejected();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleRejected]);

  const view = data.view ?? live.view;
  const running = view?.status === "running";
  const now = useNow(running);
  if (followed && (live.conn.notFound || data.notFound)) return <NotFound runId={followed} />;
  if (!followed || !view) return <EmptyLive />;

  const run = settled(view);
  const { detail, files, context, report } = data;
  const elapsed = elapsedSeconds(run, now);
  const attachments = detail?.request?.request.attachments?.length ?? files.length;

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

  return (
    <div className={css.live}>
      <LiveHeader
        run={run}
        detail={detail}
        files={attachments}
        isPhone={isPhone}
        cancelling={cancelling}
        onCancel={() => void attempt(cancel)}
        onOpenReport={() => go({ screen: "report", runId: run.runId })}
        onRerun={() => void attempt(rerun)}
      />
      <StatusBanner
        run={run}
        conn={live.conn}
        elapsed={elapsed}
        rewriteOf={detail?.fork_from === "write" ? detail.parent_run_id : null}
      />
      {isPhone && <PhoneTabs tab={liveTab} onTab={setLiveTab} counts={counts} />}
      {shows("progress") && <PhaseTimeline run={run} />}
      <div className={css.grid}>
        {(shows("progress") || shows("sources")) && (
          <div className={css.column}>
            {shows("progress") && <SubQueriesPanel run={run} className={css.subQueries} />}
            {shows("sources") && (
              <SourcesPanel run={run} files={files} context={context} className={css.sources} />
            )}
          </div>
        )}
        {shows("passages") && (
          <PassagesPanel
            run={run}
            context={context}
            marker={marker}
            rejected={data.rejected}
            showRejected={showRejected}
            onToggle={toggleRejected}
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
    </div>
  );
}

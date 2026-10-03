// The Report screen: a run's cited report (or, for the context recipe, its selected
// passages), its sources and passages, exports, versions, and Rewrite. Keyed by run id.
import { BracketsCurly, Copy, DownloadSimple, GitBranch, PenNib } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { RunSummary } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { StatusTag } from "../../components/StatusTag";
import { dateTime } from "../../format";
import { CitationTooltip, useCitation } from "../../run/CitationTooltip";
import { fmtElapsed, wDiff, wSummary } from "../../run/format";
import { lineage } from "../../run/lineage";
import { References, ReportMarkdown } from "../../run/ReportMarkdown";
import { useRun } from "../../run/useRun";
import { useRunData } from "../../run/useRunData";
import { recipeOf } from "../live/model";
import { contextJson, download, markdownFile } from "./exportReport";
import { ReportAside, SelectedPassages } from "./ReportAside";
import css from "./ReportScreen.module.css";
import { RewriteDialog } from "./RewriteDialog";
import { VersionsNav } from "./VersionsNav";

export function ReportScreen({ runId }: { runId: string }) {
  const api = useApi();
  const { toast } = useUi();
  const { view: own } = useRun(runId);
  const { detail, view, files, context, report } = useRunData(runId, own);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [rewriting, setRewriting] = useState(false);
  const { cite, onCite, onLeave } = useCitation();

  useEffect(() => {
    api.listRuns().then(setRuns, () => {});
  }, [api]);

  if (!detail) return null;
  const versions = lineage(runs, runId);
  const parent = runs.find((r) => r.run_id === detail.parent_run_id);
  const recipe = recipeOf(detail.until);
  const marker = detail.writing.citation_marker;
  const web = Object.values(view?.sources ?? {}).filter((s) => s.kind === "web");
  const sourceCount = web.filter((s) => s.state !== "failed").length + files.length;
  const passageCount = context?.passages.length ?? 0;
  const meta = [
    dateTime(detail.created),
    detail.duration_s == null ? "–" : fmtElapsed(detail.duration_s),
    recipe,
    `${sourceCount} sources`,
    `${passageCount} passages`,
  ].join(" · ");

  async function copy(text: string, message: string) {
    await navigator.clipboard?.writeText(text).catch(() => {});
    toast(message);
  }

  async function withReport(use: (markdown: string) => void | Promise<void>) {
    try {
      await use(await api.getArtifact(runId, "report.md"));
    } catch (e) {
      toast((e as Error).message);
    }
  }

  const query = detail.query;
  return (
    <div className={css.page}>
      <div className={css.inner}>
        <header className={css.header}>
          <div className={css.line}>
            <StatusTag status={detail.status} />
            <span className={css.id}>{runId}</span>
            <span>{meta}</span>
          </div>
          <h1 className={css.h1}>{query}</h1>
          <div className={css.actions}>
            {recipe === "report" && (
              <>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setRewriting(true)}
                >
                  <PenNib aria-hidden="true" />
                  Rewrite
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void withReport((md) => copy(md, "Markdown copied"))}
                >
                  <Copy aria-hidden="true" />
                  Copy markdown
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() =>
                    void withReport((md) => {
                      download(`${runId}.md`, markdownFile(query, md));
                      toast(`Downloaded ${runId}.md`);
                    })
                  }
                >
                  <DownloadSimple aria-hidden="true" />
                  Download .md
                </button>
              </>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!context}
              onClick={() =>
                context &&
                void copy(
                  JSON.stringify(contextJson(detail, context), null, 2),
                  "Context JSON copied",
                )
              }
            >
              <BracketsCurly aria-hidden="true" />
              Copy JSON (context)
            </button>
          </div>
        </header>
        <VersionsNav versions={versions} />
        <div className={css.grid}>
          <article className={css.article}>
            {parent && (
              <div className={css.parentNote}>
                <GitBranch className={css.parentIcon} aria-hidden="true" />
                Rewritten from {parent.run_id} (v{parent.version ?? 1}): same sources and passages;
                changed {wDiff(parent.writing, detail.writing) || "nothing"}.
              </div>
            )}
            {recipe === "context" ? (
              <SelectedPassages context={context} marker={marker} />
            ) : (
              <>
                <div className={css.optsLine}>
                  Written with {wSummary(detail.writing)}
                  {detail.writing.tone_instructions ? " · custom instructions" : ""}
                </div>
                {report && (
                  <>
                    <ReportMarkdown
                      body={report.body}
                      marker={marker}
                      context={context}
                      variant="article"
                      onCite={onCite}
                      onLeave={onLeave}
                    />
                    <References entries={report.references.map((r) => r.entry)} variant="article" />
                  </>
                )}
              </>
            )}
          </article>
          <ReportAside run={view} files={files} context={context} marker={marker} />
        </div>
      </div>
      {rewriting && (
        <RewriteDialog
          run={detail}
          sources={sourceCount}
          passages={passageCount}
          nextVersion={Math.max(0, ...versions.map((v) => v.run.version ?? 1)) + 1}
          onClose={() => setRewriting(false)}
        />
      )}
      <CitationTooltip cite={cite} context={context} marker={marker} />
    </div>
  );
}

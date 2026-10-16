// The Report screen: a run's cited report (or, for the context recipe, its selected
// passages), its sources and passages, exports, versions, and Rewrite. Keyed by run id.
// A catalog run whose output is a report only shows here too: a Records action instead of
// Rewrite, the cited records in the aside, and citations that open the record.
import {
  ArrowBendDownRight,
  BracketsCurly,
  Copy,
  GitBranch,
  PenNib,
  Pulse,
  Scissors,
  Table,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Report } from "../../api/generated";
import type { RunSummary, WritingOptions } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { go } from "../../app/route";
import { DepthTag } from "../../components/DepthTag";
import { HelpTip } from "../../components/HelpTip";
import { ProfileLine } from "../../components/ProfileLine";
import { isLongQuery, QueryToggle } from "../../components/QueryToggle";
import { StatusTag } from "../../components/StatusTag";
import { ThinkingTag } from "../../components/ThinkingTag";
import { dateTime } from "../../format";
import { CitationTooltip, useCitation } from "../../run/CitationTooltip";
import { aSummary, fmtElapsed, modelDiff, recipeOf, wDiff, wSummary } from "../../run/format";
import { lineage } from "../../run/lineage";
import { openRecord, RecordPopover, useRecordCitation } from "../../run/RecordCitation";
import { References, ReportMarkdown } from "../../run/ReportMarkdown";
import { useRun } from "../../run/useRun";
import { useRunData } from "../../run/useRunData";
import { CatalogScreen } from "../catalog/CatalogScreen";
import { NotFound } from "../live/NotFound";
import { Downloads } from "./Downloads";
import { contextJson, download, markdownFile } from "./exportReport";
import { CatalogReportAside, ReportAside, SelectedPassages } from "./ReportAside";
import css from "./ReportScreen.module.css";
import { RewriteDialog } from "./RewriteDialog";
import { VersionsNav } from "./VersionsNav";

/** A catalog summary may carry no writing options; the report still renders with these. */
const DEFAULT_WRITING: WritingOptions = {
  format: "report",
  tone: "objective",
  tone_instructions: "",
  words: 1200,
  language: "english",
  citation_marker: "numeric",
  reference_style: "APA",
};

export function ReportScreen({ runId }: { runId: string }) {
  const api = useApi();
  const { toast, isPhone } = useUi();
  const { view: own } = useRun(runId);
  const { detail, notFound, view, files, context, report, skips } = useRunData(runId, own);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [rewriting, setRewriting] = useState(false);
  const [queryOpen, setQueryOpen] = useState(false);
  const { cite, onCite, onLeave } = useCitation();
  const records = useRecordCitation();
  // A stable chip handler, so the report's chips are not remounted on every render.
  const pickRef = useRef<(n: number) => void>(() => {});
  const onPick = useCallback((n: number) => pickRef.current(n), []);

  useEffect(() => {
    api.listRuns().then(setRuns, () => {});
  }, [api]);

  if (notFound) return <NotFound runId={runId} />;
  if (!detail) return null;
  const catalog = detail.kind === "catalog";
  if (catalog && detail.output !== "report") {
    return <CatalogScreen runId={runId} detail={detail} />;
  }
  const writing = detail.writing ?? DEFAULT_WRITING;
  const versions = lineage(runs, runId);
  const parent = runs.find((r) => r.run_id === detail.parent_run_id);
  const recipe = recipeOf(detail.until, writing.format);
  const marker = writing.citation_marker;
  const web = Object.values(view?.sources ?? {}).filter((s) => s.kind === "web");
  const sourceCount = web.filter((s) => s.state !== "failed").length + files.length;
  const passageCount = context?.passages.length ?? 0;
  const meta = (
    catalog
      ? [
          dateTime(detail.created),
          detail.duration_s == null ? "–" : fmtElapsed(detail.duration_s),
          "catalog",
          `${detail.nodes ?? 0} nodes`,
          `${context?.sources.length ?? 0} sources`,
        ]
      : [
          dateTime(detail.created),
          detail.duration_s == null ? "–" : fmtElapsed(detail.duration_s),
          recipe,
          `${sourceCount} sources`,
          `${passageCount} passages`,
          ...(detail.rounds_planned && detail.rounds_planned > 1 && detail.rounds_ran
            ? [`${detail.rounds_ran} of ${detail.rounds_planned} rounds`]
            : []),
        ]
  ).join(" · ");
  const pick = (n: number) => {
    const id = context?.passages.find((p) => p.n === n)?.record_id;
    records.hide();
    if (id) openRecord(runId, id);
  };
  pickRef.current = pick;

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
  const long = isLongQuery(query);
  return (
    <div className={css.page}>
      <div className={css.inner}>
        <header className={css.header}>
          <div className={css.line}>
            <StatusTag status={detail.status} />
            <DepthTag depth={detail.depth} />
            <ThinkingTag reasoning={detail.reasoning} />
            <span className={css.id}>{runId}</span>
            <span>{meta}</span>
          </div>
          <ProfileLine run={detail} isPhone={isPhone} />
          <h1
            id={long ? "rep-q" : undefined}
            className={`${css.h1} ${long ? (queryOpen ? css.h1Full : css.h1Clamped) : ""}`}
          >
            {query}
          </h1>
          {long && (
            <QueryToggle
              query={query}
              open={queryOpen}
              controls="rep-q"
              onToggle={() => setQueryOpen(!queryOpen)}
            />
          )}
          <div className={css.actions}>
            {catalog && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => go({ screen: "catalog", runId, records: true })}
              >
                <Table aria-hidden="true" />
                Records
              </button>
            )}
            {recipe !== "context" && (
              <>
                {!catalog && (
                  <span className={`${css.withHelp} ${css.rewrite}`}>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => setRewriting(true)}
                    >
                      <PenNib aria-hidden="true" />
                      Rewrite
                    </button>
                    <HelpTip help="rewrite" />
                  </span>
                )}
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void withReport((md) => copy(md, "Markdown copied"))}
                >
                  <Copy aria-hidden="true" />
                  Copy markdown
                </button>
                <Downloads
                  runId={runId}
                  markdown={() =>
                    withReport((md) => {
                      download(`${runId}.md`, markdownFile(query, md));
                      toast(`Downloaded ${runId}.md`);
                    })
                  }
                />
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
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => go({ screen: "live", runId })}
            >
              <Pulse aria-hidden="true" />
              Live view
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
                changed{" "}
                {[modelDiff(parent, detail), wDiff(parent.writing, detail.writing)]
                  .filter(Boolean)
                  .join(" · ") || "nothing"}
                .
              </div>
            )}
            {recipe === "context" ? (
              <SelectedPassages context={context} marker={marker} />
            ) : (
              <>
                <div className={css.optsLine}>
                  {recipe === "answer" ? aSummary(writing) : `Written with ${wSummary(writing)}`}
                  {writing.tone_instructions ? " · custom instructions" : ""}
                </div>
                {report && <ContinuationNote report={report} />}
                {report && (
                  <>
                    <ReportMarkdown
                      body={report.body}
                      marker={marker}
                      context={context}
                      variant="article"
                      onCite={catalog ? records.onCite : onCite}
                      onLeave={catalog ? records.onLeave : onLeave}
                      onPick={catalog ? onPick : undefined}
                    />
                    {report.truncated && (
                      <div className={css.cutEnd}>
                        <Scissors aria-hidden="true" />
                        Output limit reached here
                      </div>
                    )}
                    <References
                      entries={report.references.map((r) => r.entry)}
                      style={writing.reference_style}
                      variant="article"
                    />
                  </>
                )}
              </>
            )}
          </article>
          {catalog ? (
            <CatalogReportAside
              context={context}
              cited={report?.cited ?? []}
              marker={marker}
              onOpen={(id) => openRecord(runId, id)}
            />
          ) : (
            <ReportAside
              run={view}
              created={detail?.created}
              rounds={detail?.rounds_planned ?? 1}
              files={files}
              context={context}
              marker={marker}
            />
          )}
        </div>
      </div>
      {rewriting && (
        <RewriteDialog
          run={detail}
          sources={sourceCount}
          scored={passageCount + (skips?.length ?? 0)}
          nextVersion={Math.max(0, ...versions.map((v) => v.run.version ?? 1)) + 1}
          onClose={() => setRewriting(false)}
        />
      )}
      <CitationTooltip cite={cite} context={context} marker={marker} />
      {catalog && (
        <RecordPopover
          cite={records.cite}
          context={context}
          marker={marker}
          onOpen={(id) => {
            records.hide();
            openRecord(runId, id);
          }}
          onKeep={records.keep}
          onLeave={records.onLeave}
        />
      )}
    </div>
  );
}

/** "Continued N×" for a report the writer continued, or the cut note for one still cut off. */
function ContinuationNote({ report }: { report: Report }) {
  const count = report.continuations ?? 0;
  if (report.truncated) {
    return (
      <div role="note" className={css.cutNote}>
        <Scissors className={css.cutIcon} aria-hidden="true" />
        <span>
          {count
            ? `Still cut off after ${count} continuations. The last section may be incomplete.`
            : "Cut off at the output limit. The last section may be incomplete."}
        </span>
      </div>
    );
  }
  if (!count) return null;
  return (
    <div className={css.contNote}>
      <ArrowBendDownRight className={css.contIcon} aria-hidden="true" />
      Continued {count}× after reaching the output limit.
      <HelpTip help="cont" />
    </div>
  );
}

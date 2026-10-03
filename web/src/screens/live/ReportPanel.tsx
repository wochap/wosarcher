// The Live run's report as it streams, with citation chips and a caret, kept scrolled to the
// bottom while the reader is near it; before writing, the waiting texts.
import { Cpu, Hourglass, type Icon, StopCircle } from "@phosphor-icons/react";
import { useLayoutEffect, useRef } from "react";
import type { Context, Report } from "../../api/generated";
import type { WritingOptions } from "../../api/types";
import { describeValue } from "../../components/WritingOptionsForm";
import { fmtK } from "../../run/format";
import { type CiteHandlers, ReportMarkdown } from "../../run/ReportMarkdown";
import type { RunView } from "../../run/reducer";
import { FailureCard } from "./FailureCard";
import { unloading } from "./model";
import panel from "./Panel.module.css";
import { writeTokens } from "./PhaseTimeline";
import css from "./ReportPanel.module.css";

export const STICK_PX = 140;

type Props = CiteHandlers & {
  run: RunView;
  report: Report | null;
  context: Context | null;
  writing: WritingOptions | null;
  isPhone: boolean;
  className?: string;
};

function waiting(run: RunView): { text: string; icon: Icon; warn?: boolean } {
  const write = run.phases.write;
  if (run.status === "cancelled") {
    return { text: "Cancelled before the write stage. Nothing was written.", icon: StopCircle };
  }
  if (write.state === "waiting") {
    return {
      text: `Writer is waiting for the GPU while the ${unloading(write.waitReason)} unloads.`,
      icon: Cpu,
      warn: true,
    };
  }
  if (run.until === "select") {
    return {
      text: "This run stops after selecting passages; no report is written.",
      icon: Hourglass,
    };
  }
  return { text: "The report streams here once passages are selected.", icon: Hourglass };
}

export function ReportPanel(props: Props) {
  const { run, report, context, writing, isPhone, onCite, onLeave } = props;
  const body = useRef<HTMLDivElement>(null);
  const near = useRef(true);
  const streaming = run.phases.write.state === "running";
  const written = run.phases.write.state === "done" || run.phases.write.state === "reused";
  // The streamed text has the `[n]` markers; the final snapshot is rendered, so use report.json.
  const text = written && report ? report.body : run.report;
  const failed = run.status === "failed" || run.status === "interrupted";

  useLayoutEffect(() => {
    const el = body.current;
    if (el && near.current && text) el.scrollTop = el.scrollHeight;
  }, [text]);

  const tokens = fmtK(writeTokens(run));
  const summary = text ? (streaming ? `writing · ${tokens} tokens` : `${tokens} tokens`) : "";
  const options =
    writing && !isPhone
      ? [
          describeValue("tone", writing.tone),
          describeValue("words", writing.words),
          describeValue("language", writing.language),
        ].join(" · ")
      : "";
  const empty = !text && !failed ? waiting(run) : null;
  const EmptyIcon = empty?.icon ?? Hourglass;

  return (
    <section aria-label="Report" className={`${panel.panel} ${props.className ?? ""}`}>
      <header className={panel.header}>
        <h2 className={panel.title}>Report</h2>
        <span className={panel.summary}>{summary}</span>
        <span className={css.options}>{options}</span>
      </header>
      <div
        ref={body}
        className={`${panel.body} ${css.body}`}
        data-testid="report-body"
        onScroll={(e) => {
          const el = e.currentTarget;
          near.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
        }}
      >
        {empty && (
          <div className={css.empty}>
            <EmptyIcon
              className={panel.emptyIcon}
              data-tone={empty.warn ? "warn" : undefined}
              aria-hidden="true"
            />
            <span>{empty.text}</span>
          </div>
        )}
        {failed && <FailureCard run={run} />}
        {text && (
          <ReportMarkdown
            body={text}
            streaming={streaming}
            marker={writing?.citation_marker ?? "numeric"}
            context={context}
            variant="live"
            onCite={onCite}
            onLeave={onLeave}
          />
        )}
      </div>
    </section>
  );
}

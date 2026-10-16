// The Live run header: status tag, depth tag, rewrite tag, id, meta, query, device chip, and actions.

import { ArrowClockwise, Article, Circle, GitBranch, Stop, Table } from "@phosphor-icons/react";
import { useState } from "react";
import type { RunDetail, RunKind, RunStatus } from "../../api/types";
import { DepthTag } from "../../components/DepthTag";
import { HelpTip } from "../../components/HelpTip";
import { OriginLabel } from "../../components/OriginLabel";
import { ProfileLine } from "../../components/ProfileLine";
import { isLongQuery, QueryToggle } from "../../components/QueryToggle";
import { ThinkingTag } from "../../components/ThinkingTag";
import { recipeOf } from "../../run/format";
import type { RunView } from "../../run/reducer";
import { DeviceChip } from "./DeviceChip";
import css from "./LiveHeader.module.css";

const LABELS: Record<RunStatus, string> = {
  queued: "Connecting",
  running: "Running",
  waiting: "Waiting",
  done: "Completed",
  failed: "Failed",
  interrupted: "Interrupted",
  cancelled: "Cancelled",
};

type Props = {
  run: RunView;
  detail: RunDetail | null;
  files: number;
  isPhone: boolean;
  /** A catalog run: "catalog" leads the meta and the done action is "Open catalog". */
  kind?: RunKind;
  /** A catalog run whose output is `report`: the done action is "Open report". */
  reportOnly?: boolean;
  /** A cancel request is in flight. */
  cancelling: boolean;
  onCancel: () => void;
  onOpenReport: () => void;
  onRerun: () => void;
};

export function LiveHeader({
  run,
  detail,
  files,
  isPhone,
  kind = "research",
  reportOnly = false,
  cancelling,
  onCancel,
  onOpenReport,
  onRerun,
}: Props) {
  const status = run.status;
  const active = status === "queued" || status === "running" || status === "waiting";
  const ended = status === "failed" || status === "cancelled" || status === "interrupted";
  // The profile line names the profile; a run without one keeps it in the meta line.
  const catalog = kind === "catalog";
  const meta = [
    catalog ? "catalog" : recipeOf(run.until ?? detail?.until, detail?.writing.format),
    detail?.sources ?? "both",
    ...(detail?.use ? [] : [run.profile ?? detail?.profile ?? ""]),
  ];
  if (files) meta.push(`${files} file${files > 1 ? "s" : ""}`);
  const parent = run.parentRunId ?? detail?.parent_run_id;
  const query = run.query ?? detail?.query ?? "";
  const long = isLongQuery(query);
  const [open, setOpen] = useState(false);
  const expanded = long && open;
  return (
    <header className={css.header}>
      <div className={css.main}>
        <div className={css.line}>
          <span className={`tag ${css.status}`} data-state={status} data-queued={!!run.queued}>
            <Circle weight="fill" className={css.dot} aria-hidden="true" />
            {status === "queued" && run.queued ? "Queued" : LABELS[status]}
          </span>
          {!catalog && <DepthTag depth={detail?.depth} />}
          <ThinkingTag reasoning={detail?.reasoning} />
          {detail?.fork_from === "write" && parent && (
            <span className={`tag tag-outline ${css.rewrite}`}>
              <GitBranch aria-hidden="true" />
              rewrite of {parent}
            </span>
          )}
          <OriginLabel origin={detail?.origin} tokenName={detail?.token_name} />
          <span className={css.id}>{run.runId}</span>
          <span>{meta.join(" · ")}</span>
        </div>
        {detail && <ProfileLine run={detail} isPhone={isPhone} />}
        <div id="run-q" className={expanded ? css.queryFull : css.query}>
          {query}
        </div>
        {long && (
          <QueryToggle
            query={query}
            open={expanded}
            controls="run-q"
            onToggle={() => setOpen(!open)}
          />
        )}
      </div>
      <div className={css.actions}>
        {active && !isPhone && <DeviceChip run={run} />}
        {active && (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={cancelling}
            onClick={onCancel}
          >
            <Stop aria-hidden="true" />
            Cancel
          </button>
        )}
        {status === "done" && (
          <button type="button" className="btn btn-primary" onClick={onOpenReport}>
            {catalog && !reportOnly ? <Table aria-hidden="true" /> : <Article aria-hidden="true" />}
            {catalog && !reportOnly ? "Open catalog" : "Open report"}
          </button>
        )}
        {ended && (
          <span className={css.rerun}>
            <button type="button" className="btn btn-secondary" onClick={onRerun}>
              <ArrowClockwise aria-hidden="true" />
              Rerun
            </button>
            <HelpTip help="rerun" />
          </span>
        )}
      </div>
    </header>
  );
}

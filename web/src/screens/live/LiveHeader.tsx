// The Live run header: status tag, depth tag, rewrite tag, id, meta, query, device chip, and actions.

import { ArrowClockwise, Article, Circle, GitBranch, Stop } from "@phosphor-icons/react";
import { useState } from "react";
import type { RunDetail, RunStatus } from "../../api/types";
import { DepthTag } from "../../components/DepthTag";
import { HelpTip } from "../../components/HelpTip";
import { isLongQuery, QueryToggle } from "../../components/QueryToggle";
import type { RunView } from "../../run/reducer";
import { DeviceChip } from "./DeviceChip";
import css from "./LiveHeader.module.css";
import { recipeOf } from "./model";

const LABELS: Record<RunStatus, string> = {
  queued: "Connecting",
  running: "Running",
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
  cancelling,
  onCancel,
  onOpenReport,
  onRerun,
}: Props) {
  const status = run.status;
  const active = status === "queued" || status === "running";
  const ended = status === "failed" || status === "cancelled" || status === "interrupted";
  const meta = [
    recipeOf(run.until ?? detail?.until),
    detail?.sources ?? "both",
    run.profile ?? detail?.profile ?? "",
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
          <span className={`tag ${css.status}`} data-state={status}>
            <Circle weight="fill" className={css.dot} aria-hidden="true" />
            {LABELS[status]}
          </span>
          <DepthTag depth={detail?.depth} />
          {detail?.fork_from === "write" && parent && (
            <span className={`tag tag-outline ${css.rewrite}`}>
              <GitBranch aria-hidden="true" />
              rewrite of {parent}
            </span>
          )}
          <span className={css.id}>{run.runId}</span>
          <span>{meta.join(" · ")}</span>
        </div>
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
            <Article aria-hidden="true" />
            Open report
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

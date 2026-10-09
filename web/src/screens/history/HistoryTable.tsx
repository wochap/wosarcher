// The Run history table. Every column comes from the one GET /api/runs response.
import {
  ArrowClockwise,
  ArrowElbowDownRight,
  ArrowSquareOut,
  Pulse,
  Trash,
} from "@phosphor-icons/react";
import type { RunSummary } from "../../api/types";
import { DepthTag } from "../../components/DepthTag";
import { HelpTip } from "../../components/HelpTip";
import { StatusTag } from "../../components/StatusTag";
import { dateTime, minSec } from "../../format";
import { recipeOf, wDiff } from "../../run/format";
import css from "./HistoryTable.module.css";

export const durationOf = (run: RunSummary) =>
  run.duration_s == null ? "–" : minSec(run.duration_s);
export const costOf = (run: RunSummary) => (run.cost == null ? "–" : `$${run.cost.toFixed(3)}`);

type Props = {
  runs: RunSummary[];
  all: RunSummary[];
  onOpen: (run: RunSummary) => void;
  onOpenLive: (run: RunSummary) => void;
  onRerun: (run: RunSummary) => void;
  onDelete: (run: RunSummary) => void;
};

export function HistoryTable({ runs, all, onOpen, onOpenLive, onRerun, onDelete }: Props) {
  return (
    <div className={css.scroll}>
      <table className={`table ${css.table}`}>
        <thead>
          <tr>
            <th className={css.queryCol}>Query</th>
            <th>Date</th>
            <th>
              <span className={css.thHelp}>
                Recipe
                <HelpTip help="h-recipe" />
              </span>
            </th>
            <th>Status</th>
            <th className={css.num}>Duration</th>
            <th className={css.num}>
              <span className={css.thHelp}>
                Cost
                <HelpTip help="h-cost" />
              </span>
            </th>
            <th className={css.num}>
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const parent = run.parent_run_id
              ? all.find((r) => r.run_id === run.parent_run_id)
              : undefined;
            return (
              <tr key={run.run_id}>
                <td className={css.queryCell}>
                  <button type="button" className={css.open} onClick={() => onOpen(run)}>
                    {run.query}
                  </button>
                  {run.parent_run_id && (
                    <div className={css.rewrite}>
                      <ArrowElbowDownRight aria-hidden="true" />
                      rewrite of <span className={css.id}>{run.parent_run_id}</span> ·{" "}
                      {parent ? wDiff(parent.writing, run.writing) || "same options" : "–"}
                      <HelpTip help="h-version" label="Rewrite marker" />
                    </div>
                  )}
                </td>
                <td className={css.date}>{dateTime(run.created)}</td>
                <td>{recipeOf(run.until, run.writing.format)}</td>
                <td>
                  <div className={css.tags}>
                    <StatusTag status={run.status} />
                    <DepthTag depth={run.depth} />
                  </div>
                </td>
                <td className={css.num}>{durationOf(run)}</td>
                <td className={css.num}>{costOf(run)}</td>
                <td className={css.num}>
                  <div className={css.actions}>
                    <button
                      type="button"
                      className={`btn btn-ghost btn-icon ${css.action}`}
                      aria-label="Open"
                      title="Open"
                      onClick={() => onOpen(run)}
                    >
                      <ArrowSquareOut aria-hidden="true" />
                    </button>
                    {run.status === "done" && (
                      <button
                        type="button"
                        className={`btn btn-ghost btn-icon ${css.action}`}
                        aria-label="Live view"
                        title="Live view"
                        onClick={() => onOpenLive(run)}
                      >
                        <Pulse aria-hidden="true" />
                      </button>
                    )}
                    <button
                      type="button"
                      className={`btn btn-ghost btn-icon ${css.action}`}
                      aria-label="Rerun"
                      title="Rerun"
                      onClick={() => onRerun(run)}
                    >
                      <ArrowClockwise aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className={`btn btn-ghost btn-icon ${css.action} ${css.delete}`}
                      aria-label="Delete"
                      title="Delete"
                      onClick={() => onDelete(run)}
                    >
                      <Trash aria-hidden="true" />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

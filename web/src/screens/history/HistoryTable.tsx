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
import { OriginLabel } from "../../components/OriginLabel";
import { StatusTag } from "../../components/StatusTag";
import { dateTime, minSec } from "../../format";
import { modelDiff, recipeOf, wDiff } from "../../run/format";
import css from "./HistoryTable.module.css";

export const durationOf = (run: RunSummary) =>
  run.duration_s == null ? "–" : minSec(run.duration_s);
export const costOf = (run: RunSummary) => (run.cost == null ? "–" : `$${run.cost.toFixed(3)}`);

/** The Recipe column: the recipe, or "<n> nodes" for a catalog run ("–" while null). */
export function recipeLabel(run: RunSummary): string {
  if (run.kind === "catalog") return run.nodes == null ? "–" : `${run.nodes} nodes`;
  return recipeOf(run.until, run.writing?.format);
}

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
            <th>Kind</th>
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
                  <div className={css.queryLine}>
                    <OriginLabel origin={run.origin} tokenName={run.token_name} />
                    <button type="button" className={css.open} onClick={() => onOpen(run)}>
                      {run.query}
                    </button>
                  </div>
                  {run.parent_run_id && run.kind === "catalog" && (
                    <div className={css.rewrite}>
                      <ArrowElbowDownRight aria-hidden="true" />
                      {run.fork_from === "extract" ? "re-extracted from" : "expanded from"}{" "}
                      <span className={css.id}>{run.parent_run_id}</span>
                    </div>
                  )}
                  {run.parent_run_id && run.kind !== "catalog" && (
                    <div className={css.rewrite}>
                      <ArrowElbowDownRight aria-hidden="true" />
                      rewrite of <span className={css.id}>{run.parent_run_id}</span> ·{" "}
                      {parent
                        ? [modelDiff(parent, run), wDiff(parent.writing, run.writing)]
                            .filter(Boolean)
                            .join(" · ") || "same options"
                        : "–"}
                      <HelpTip help="h-version" label="Rewrite marker" />
                    </div>
                  )}
                </td>
                <td className={css.date}>{dateTime(run.created)}</td>
                <td>
                  <span
                    className={`tag ${run.kind === "catalog" ? "tag-accent" : "tag-outline"} ${css.kind}`}
                  >
                    {run.kind === "catalog" ? "catalog" : "research"}
                  </span>
                </td>
                <td className={css.recipe}>{recipeLabel(run)}</td>
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

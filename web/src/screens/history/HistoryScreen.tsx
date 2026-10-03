// Run history: search, Status and Recipe filters, the table, and the empty states.
import { ClockCounterClockwise, MagnifyingGlass, Plus } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { RunSummary } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { SEARCH_ID } from "../../app/keys";
import { go } from "../../app/route";
import page from "../../components/Page.module.css";
import { Seg } from "../../components/Seg";
import css from "./HistoryScreen.module.css";
import { HistoryTable, recipeOf } from "./HistoryTable";

type StatusFilter = "all" | "completed" | "failed" | "cancelled";
type RecipeFilter = "any" | "report" | "context";

const STATUS_MATCH: Record<StatusFilter, (r: RunSummary) => boolean> = {
  all: () => true,
  completed: (r) => r.status === "done",
  failed: (r) => r.status === "failed" || r.status === "interrupted",
  cancelled: (r) => r.status === "cancelled",
};

export function HistoryScreen() {
  const api = useApi();
  const { hiddenRuns, deleteRun, follow, toast } = useUi();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [recipe, setRecipe] = useState<RecipeFilter>("any");

  useEffect(() => {
    api.listRuns().then(
      (list) => setRuns([...list].sort((a, b) => b.created.localeCompare(a.created))),
      () => {},
    );
  }, [api]);

  if (!runs) return null;
  const all = runs.filter((r) => !hiddenRuns.has(r.run_id));
  const needle = query.trim().toLowerCase();
  const shown = all.filter(
    (r) =>
      (!needle || r.query.toLowerCase().includes(needle)) &&
      STATUS_MATCH[status](r) &&
      (recipe === "any" || recipeOf(r) === recipe),
  );

  async function rerun(run: RunSummary) {
    try {
      const created = await api.rerunRun(run.run_id);
      follow(created.run_id);
      go({ screen: "live", runId: created.run_id });
    } catch (e) {
      toast((e as Error).message);
    }
  }

  return (
    <div className={page.page}>
      <div className={`${page.inner} ${css.inner}`}>
        <div className={css.title}>
          <h1 className={page.h1}>Run history</h1>
          <span className={css.count}>{all.length || ""}</span>
        </div>
        <div className={css.filters}>
          <div className={css.search}>
            <MagnifyingGlass className={css.searchIcon} aria-hidden="true" />
            <input
              id={SEARCH_ID}
              className="input"
              aria-label="Search runs"
              placeholder="Search queries   /"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <Seg
            label="Status"
            name="hf"
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "All" },
              { value: "completed", label: "Completed" },
              { value: "failed", label: "Failed" },
              { value: "cancelled", label: "Cancelled" },
            ]}
          />
          <Seg
            label="Recipe"
            name="hr"
            value={recipe}
            onChange={setRecipe}
            options={[
              { value: "any", label: "Any recipe" },
              { value: "report", label: "report" },
              { value: "context", label: "context" },
            ]}
          />
        </div>
        {shown.length ? (
          <HistoryTable
            runs={shown}
            all={all}
            onOpen={(r) =>
              go(
                r.status === "done"
                  ? { screen: "report", runId: r.run_id }
                  : { screen: "live", runId: r.run_id },
              )
            }
            onRerun={rerun}
            onDelete={(r) => deleteRun(r.run_id)}
          />
        ) : (
          <div className={css.empty}>
            <ClockCounterClockwise className={css.emptyIcon} aria-hidden="true" />
            <div className={css.emptyTitle}>{all.length ? "No runs match" : "No runs yet"}</div>
            <div className={css.emptyText}>
              {!all.length
                ? "Finished, failed and cancelled runs are kept here with their reports."
                : needle
                  ? `Nothing matches “${query}” with these filters.`
                  : "Nothing matches these filters."}
            </div>
            {all.length ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setQuery("");
                  setStatus("all");
                  setRecipe("any");
                }}
              >
                Clear filters
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => go({ screen: "new" })}
              >
                <Plus aria-hidden="true" />
                New run
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

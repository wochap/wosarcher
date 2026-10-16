// Run history: search, Status and Recipe filters, the table, and the empty states.
import { ClockCounterClockwise, MagnifyingGlass, Plus } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import type { RunSummary } from "../../api/types";
import { useApi, useUi } from "../../app/context";
import { SEARCH_ID } from "../../app/keys";
import { go, type Route } from "../../app/route";
import page from "../../components/Page.module.css";
import { Seg } from "../../components/Seg";
import { type Recipe, recipeOf } from "../../run/format";
import css from "./HistoryScreen.module.css";
import { HistoryTable } from "./HistoryTable";

type StatusFilter = "all" | "completed" | "failed" | "cancelled";
type RecipeFilter = "any" | Recipe;
type KindFilter = "any" | "research" | "catalog";

const isCatalog = (r: RunSummary) => r.kind === "catalog";

/** Rows the search and the Kind, Status, and Recipe filters keep; a recipe hides catalog runs. */
export function historyFilter(
  runs: RunSummary[],
  f: { query: string; kind: KindFilter; status: StatusFilter; recipe: RecipeFilter },
): RunSummary[] {
  const needle = f.query.trim().toLowerCase();
  return runs.filter(
    (r) =>
      (!needle || r.query.toLowerCase().includes(needle)) &&
      (f.kind === "any" || (f.kind === "catalog") === isCatalog(r)) &&
      STATUS_MATCH[f.status](r) &&
      (f.recipe === "any" || (!isCatalog(r) && recipeOf(r.until, r.writing?.format) === f.recipe)),
  );
}

/** Where Open goes: a finished run's result by kind, else the Live run screen. */
export function openRoute(r: RunSummary): Route {
  if (r.status !== "done") return { screen: "live", runId: r.run_id };
  return { screen: isCatalog(r) ? "catalog" : "report", runId: r.run_id };
}

const STATUS_MATCH: Record<StatusFilter, (r: RunSummary) => boolean> = {
  all: () => true,
  completed: (r) => r.status === "done",
  failed: (r) => r.status === "failed" || r.status === "interrupted",
  cancelled: (r) => r.status === "cancelled",
};

export function HistoryScreen() {
  const api = useApi();
  const { hiddenRuns, deleteRun, follow, toast, setDraft } = useUi();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [recipe, setRecipe] = useState<RecipeFilter>("any");
  const [kind, setKind] = useState<KindFilter>("any");

  useEffect(() => {
    api.listRuns().then(
      (list) => setRuns([...list].sort((a, b) => b.created.localeCompare(a.created))),
      () => {},
    );
  }, [api]);

  if (!runs) return null;
  const all = runs.filter((r) => !hiddenRuns.has(r.run_id));
  const needle = query.trim().toLowerCase();
  const shown = historyFilter(all, { query, kind, status, recipe });

  async function rerun(run: RunSummary) {
    if (isCatalog(run)) {
      // A catalog rerun opens New run with the brief and structure; nothing is sent.
      setDraft((d) => ({
        ...d,
        kind: "catalog",
        brief: run.form?.query ?? run.query,
        structure: run.form?.structure ?? null,
      }));
      go({ screen: "new" });
      return;
    }
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
            label="Kind"
            name="hk"
            value={kind}
            onChange={setKind}
            options={[
              { value: "any", label: "Any" },
              { value: "research", label: "Research" },
              { value: "catalog", label: "Catalog" },
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
              { value: "answer", label: "answer" },
              { value: "context", label: "context" },
            ]}
          />
        </div>
        {shown.length ? (
          <HistoryTable
            runs={shown}
            all={all}
            onOpen={(r) => go(openRoute(r))}
            onOpenLive={(r) => go({ screen: "live", runId: r.run_id })}
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
                  setKind("any");
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

import { describe, expect, it } from "vitest";
import type { RunSummary } from "../../api/types";
import { runs } from "../../test/fixtures/data";
import { historyFilter, openRoute } from "./HistoryScreen";
import { recipeLabel } from "./HistoryTable";

const research = runs.find((r) => r.status === "done") as RunSummary;
const catalog: RunSummary = { ...research, run_id: "r_cat", kind: "catalog", nodes: 118 };
const running: RunSummary = { ...catalog, run_id: "r_cat2", status: "running", nodes: null };
const all = [research, catalog, running];
const f = { query: "", kind: "any", status: "all", recipe: "any" } as const;

describe("history by kind", () => {
  it("filters by kind, and a recipe hides catalog runs", () => {
    expect(historyFilter(all, f)).toHaveLength(3);
    expect(historyFilter(all, { ...f, kind: "catalog" }).map((r) => r.run_id)).toEqual([
      "r_cat",
      "r_cat2",
    ]);
    expect(historyFilter(all, { ...f, kind: "research" })).toEqual([research]);
    expect(historyFilter(all, { ...f, recipe: "report" })).toEqual([research]);
  });

  it("labels the recipe of a catalog run with its nodes", () => {
    expect(recipeLabel(catalog)).toBe("118 nodes");
    expect(recipeLabel(running)).toBe("–");
    expect(recipeLabel(research)).toBe("report");
  });

  it("opens finished runs by kind and others live", () => {
    expect(openRoute(catalog)).toEqual({ screen: "catalog", runId: "r_cat" });
    expect(openRoute(research)).toEqual({ screen: "report", runId: research.run_id });
    expect(openRoute(running)).toEqual({ screen: "live", runId: "r_cat2" });
  });
});

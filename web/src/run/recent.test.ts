import { beforeEach, describe, expect, it } from "vitest";
import type { RunSummary } from "../api/types";
import { depths, profiles, runs, settings } from "../test/fixtures/data";
import {
  draftFromRun,
  loadMarks,
  pruneMarks,
  recentGroups,
  rename,
  saveMarks,
  togglePin,
} from "./recent";

const base = runs[2];
const at = (run_id: string, created: string, extra: Partial<RunSummary> = {}): RunSummary => ({
  ...base,
  run_id,
  created,
  ...extra,
});

beforeEach(() => localStorage.clear());

describe("recentGroups", () => {
  it("collapses runs with the same question, form, and attachment names into the newest", () => {
    const form = { query: base.query, depth: "quick" };
    const files = [{ name: "notes.md", size: 10 }];
    const older = at("a", "2026-10-01T00:00:00Z", { form, attachments: files });
    const newer = at("b", "2026-10-02T00:00:00Z", { form, attachments: files });
    const other = at("c", "2026-10-03T00:00:00Z", { form: { ...form, depth: "deep" } });
    const { recent } = recentGroups([older, other, newer], []);
    expect(recent.map((r) => [r.run.run_id, r.count])).toEqual([
      ["c", 1],
      ["b", 2],
    ]);
  });

  it("leaves forks and rewrites out", () => {
    const { recent } = recentGroups(runs, []);
    expect(recent.map((r) => r.run.run_id)).not.toContain("r_7f41");
    expect(recent.map((r) => r.run.run_id)).toContain("r_7f3a");
  });

  it("puts pinned runs first in pin order and keeps at most 20 recent rows", () => {
    const many = Array.from({ length: 25 }, (_, n) =>
      at(`r${n}`, `2026-10-01T00:${String(n).padStart(2, "0")}:00Z`, { query: `q${n}` }),
    );
    const { pinned, recent } = recentGroups(many, ["r3", "r1", "gone"]);
    expect(pinned.map((r) => r.run_id)).toEqual(["r3", "r1"]);
    expect(recent).toHaveLength(20);
    expect(recent[0].run.run_id).toBe("r24");
  });
});

describe("names and pins", () => {
  it("keep a pin and a name across a reload, and drop runs that are gone", () => {
    const run = runs[2];
    let marks = togglePin(loadMarks(), run.run_id);
    marks = rename(marks, run, " Weekly LLM digest ");
    saveMarks(marks);
    const loaded = loadMarks();
    expect(loaded).toEqual({ names: { [run.run_id]: "Weekly LLM digest" }, pins: [run.run_id] });
    expect(recentGroups(runs, loaded.pins).pinned.map((r) => r.run_id)).toEqual([run.run_id]);
    expect(pruneMarks(loaded, runs.slice(3))).toEqual({ names: {}, pins: [] });
  });

  it("removes the name when it is emptied or set to the question", () => {
    const run = runs[2];
    const named = rename(loadMarks(), run, "x");
    expect(rename(named, run, "  ").names).toEqual({});
    expect(rename(named, run, run.query).names).toEqual({});
  });

  it("reads broken storage as empty", () => {
    localStorage.setItem("wosarcher-run-pins", "{not json");
    expect(loadMarks()).toEqual({ names: {}, pins: [] });
  });
});

describe("draftFromRun", () => {
  const known = { profiles, depths, saved: settings.writing };

  it("fills a Custom run's values, Length, profile edits, and attachments", () => {
    const research = {
      sub_queries: 6,
      results_per_query: 8,
      max_pages: 80,
      passages_per_query: 12,
      rounds: 2,
      queries_per_round: 4,
    };
    const run = at("r1", "2026-10-01T00:00:00Z", {
      form: {
        query: base.query,
        sources: "both",
        profile: "workstation",
        depth: "custom",
        research,
        writing: { format: "report", words: 1500, tone: "critical" },
        use: { score: "rerank" },
        llm: { reasoning: { plan: "low" } },
        search_language: "es",
        domains: { allow: ["gob.pe"] },
      },
      attachments: [
        { name: "rag-chunking.md", size: 6120 },
        { name: "api-docs-sample.md", size: 900 },
      ],
    });
    const draft = draftFromRun(run, "RAG chunking", known);
    expect(draft.query).toBe(base.query);
    expect(draft.options).toEqual({
      recipe: "report",
      sources: "both",
      profile: "workstation",
      depth: "custom",
    });
    expect(draft.custom).toEqual({ values: research, words: 1500 });
    expect(draft.writing).toEqual({ tone: "critical" });
    expect(draft.use).toEqual({ score: "rerank" });
    expect(draft.profileEdits).toEqual({ plan: "low" });
    expect(draft.searchLanguage).toBe("es");
    expect(draft.domains).toEqual({ allow: ["gob.pe"] });
    expect(draft.reused).toEqual([
      { runId: "r1", runName: "RAG chunking", name: "rag-chunking.md", size: 6120 },
      { runId: "r1", runName: "RAG chunking", name: "api-docs-sample.md", size: 900 },
    ]);
  });

  it("fills a run without a form from its summary, with fallbacks for what is gone", () => {
    const run = at("r2", "2026-10-01T00:00:00Z", {
      until: "select",
      sources: "web",
      profile: "deleted-profile",
      depth: "huge",
    });
    const draft = draftFromRun(run, base.query, known);
    expect(draft.options).toEqual({ recipe: "context", sources: "web", depth: "standard" });
    expect(draft.writing).toEqual({});
    expect(draft.reused).toEqual([]);
  });
});

import { describe, expect, it } from "vitest";
import type { RunSummary } from "../api/types";
import { runs as sample, writing } from "../test/fixtures/data";
import { lineage } from "./lineage";

const base = sample[2];
const run = (run_id: string, extra: Partial<RunSummary>): RunSummary => ({
  ...base,
  run_id,
  ...extra,
});

describe("lineage", () => {
  const root = run("r1", { created: "2026-10-03T10:00:00Z", duration_s: 150 });
  const v2 = run("r2", {
    parent_run_id: "r1",
    fork_from: "write",
    version: 2,
    created: "2026-10-03T10:05:00Z",
    writing: { ...writing, tone: "concise", words: 250 },
    duration_s: 51,
  });
  const v3 = run("r3", {
    parent_run_id: "r1",
    fork_from: "write",
    version: 3,
    created: "2026-10-03T10:09:00Z",
    duration_s: 40,
  });
  const other = run("x9", {});

  it("lists a root with two rewrites, oldest first", () => {
    const versions = lineage([v3, other, v2, root], "r2");
    expect(versions.map((v) => [v.run.run_id, v.kind, v.description, v.current])).toEqual([
      ["r1", "research", "full run · 2:30", false],
      ["r2", "rewrite", "Concise · 250 words · 0:51", true],
      ["r3", "rewrite", "same options · 0:40", false],
    ]);
  });

  it("follows a fork of a fork from score", () => {
    const fork = run("r4", { parent_run_id: "r2", fork_from: "score", version: 4, duration_s: 61 });
    const versions = lineage([root, v2, fork], "r4");
    expect(versions.map((v) => v.run.run_id)).toEqual(["r1", "r2", "r4"]);
    expect(versions[2].kind).toBe("fork from score");
    expect(versions[2].description).toBe("Analytical · 1200 words · 1:01");
  });

  it("is one entry for a single run", () => {
    expect(lineage([root], "r1")).toHaveLength(1);
  });
});

import { describe, expect, it } from "vitest";
import type { Chunk, Score } from "../api/generated";
import { displayScore, rejectedPassages } from "./scores";

describe("displayScore", () => {
  it("maps each scorer to 0..1", () => {
    expect(displayScore("jev", 2.4, 3)).toBeCloseTo(0.8);
    expect(displayScore("rerank", 1.3, 1.3)).toBe(1);
    expect(displayScore("bm25", 6, 12)).toBe(0.5);
    expect(displayScore("bm25", 12, 12)).toBe(1);
    expect(displayScore("passthrough", 1, 1)).toBeNull();
  });
});

describe("rejectedPassages", () => {
  const chunk = (id: string): Chunk => ({
    chunk_id: id,
    source_id: "s1",
    position: 0,
    text: `text ${id}`,
    heading_path: ["Intro"],
  });
  const score = (chunk_id: string, query_id: string, value: number, kept: boolean): Score => ({
    chunk_id,
    query_id,
    scorer: "bm25",
    value,
    kept,
  });

  it("joins rows by chunk and skips chunks kept for any query", () => {
    const rows = [
      score("c1", "q1", 10, true),
      score("c2", "q1", 4, false),
      score("c1", "q2", 1, false),
      score("c3", "q2", 2, false),
    ];
    const out = rejectedPassages(
      rows,
      [chunk("c1"), chunk("c2"), chunk("c3")],
      { q1: 0.5, q2: 0.5 },
      { s1: { title: "Doc", uri: "https://example.org/a" } },
    );
    expect(out.map((p) => [p.chunk_id, p.display])).toEqual([
      ["c2", 0.4],
      ["c3", 1],
    ]);
    expect(out[0]).toMatchObject({ title: "Doc", threshold: 0.5, kept: false });
  });
});

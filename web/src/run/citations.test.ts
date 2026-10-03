import { describe, expect, it } from "vitest";
import type { Context } from "../api/generated";
import { citationGroups, label, prepare } from "./citations";

const context: Context = {
  query: "q",
  budget_tokens: 0,
  used_tokens: 0,
  passages: [
    { n: 1, chunk_id: "c1", source_id: "a", query_id: "q1", scorer: "rerank", text: "t" },
    { n: 2, chunk_id: "c2", source_id: "b", query_id: "q1", scorer: "rerank", text: "t" },
    { n: 3, chunk_id: "c3", source_id: "f", query_id: "q1", scorer: "rerank", text: "t" },
  ],
  sources: [
    {
      source_id: "a",
      kind: "web",
      uri: "https://x.org/p",
      title: "A",
      author: "Leviathan et al.",
      published: "2023-01-02",
    },
    { source_id: "b", kind: "web", uri: "https://www.example.org/p", title: "B" },
    { source_id: "f", kind: "file", uri: "notes/bench.md", title: "bench" },
  ],
};

describe("citations", () => {
  it("finds groups and gives one chip per number", () => {
    expect(citationGroups("a [1, 2] b [3](x) c [4]")).toEqual([
      { start: 2, end: 8, numbers: [1, 2] },
      { start: 20, end: 23, numbers: [4] },
    ]);
    expect(prepare("Hi [1, 2].", false)).toBe("Hi [1](#cite-1)[2](#cite-2).");
  });

  it("drops a trailing partial marker and appends the caret while streaming", () => {
    expect(prepare("Hi [1", true)).toBe("Hi [](#caret)");
    expect(prepare("Hi [2] and", true)).toBe("Hi [2](#cite-2) and[](#caret)");
    expect(prepare("Hi [1", false)).toBe("Hi [1");
  });

  it("labels per citation marker", () => {
    expect(label(3, "numeric", context)).toBe("[3]");
    expect(label(12, "superscript", context)).toBe("¹²");
    expect(label(1, "author-year", context)).toBe("Leviathan et al., 2023");
    expect(label(2, "author-year", context)).toBe("example.org, n.d.");
    expect(label(3, "author-year", context)).toBe("bench.md, n.d.");
  });
});

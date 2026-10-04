import { describe, expect, it } from "vitest";
import { writing } from "../test/fixtures/data";
import { fmtBytes, fmtCost, fmtElapsed, fmtK, wDiff, wSummary } from "./format";

describe("run formats", () => {
  it("formats the prototype's examples", () => {
    expect(fmtElapsed(150)).toBe("2:30");
    expect(fmtElapsed(51)).toBe("0:51");
    expect(fmtK(1234)).toBe("1.2k");
    expect(fmtK(160)).toBe("160");
    expect(fmtBytes(4403)).toBe("4.3 KB");
    expect(fmtBytes(512)).toBe("512 B");
    expect(fmtCost(0.0024)).toBe("$0.0024");
    expect(fmtCost(0)).toBe("$0.0000 · local");
  });

  it("summarizes and diffs writing options", () => {
    expect(wSummary(writing)).toBe("Analytical · 1200 words · English · [1] Numeric · APA");
    const next = { ...writing, tone: "concise", words: 250, tone_instructions: "Short." };
    expect(wDiff(writing, next)).toBe("Concise · custom instructions · 250 words");
    expect(wDiff(writing, writing)).toBe("");
  });
});

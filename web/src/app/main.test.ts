import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("main.tsx", () => {
  it("imports no remote URL", () => {
    const source = readFileSync(resolve(__dirname, "../main.tsx"), "utf8");
    const imports = [...source.matchAll(/import\s[^;]*?["']([^"']+)["']/g)].map((m) => m[1]);
    expect(imports.length).toBeGreaterThan(0);
    expect(imports.filter((i) => /^https?:/.test(i))).toEqual([]);
    expect(source).not.toMatch(/https?:\/\//);
  });
});

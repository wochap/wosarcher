import { mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { build } from "vite";
import { describe, expect, it } from "vitest";

const web = resolve(__dirname, "../..");

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? files(join(dir, entry.name)) : [join(dir, entry.name)],
  );
}

describe("dev preview", () => {
  it("is not in the production bundle", { timeout: 60_000 }, async () => {
    const outDir = mkdtempSync(join(tmpdir(), "wosarcher-build-"));
    // Vitest sets NODE_ENV=test, which Vite would read as a development build.
    const env = process.env.NODE_ENV;
    process.env.NODE_ENV = "production";
    await build({
      root: web,
      mode: "production",
      logLevel: "silent",
      build: { outDir, emptyOutDir: true },
    }).finally(() => {
      process.env.NODE_ENV = env;
    });
    const output = files(outDir);
    expect(output.some((f) => f.includes("preview"))).toBe(false);
    const code = output.filter((f) => f.endsWith(".js")).map((f) => readFileSync(f, "utf8"));
    expect(code.join("\n")).not.toContain("login-limited");
  });
});

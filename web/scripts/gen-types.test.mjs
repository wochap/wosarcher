import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { run } from "./gen-types.mjs";

const schema = () => ({
  title: "Stub",
  $defs: {
    RunCreated: {
      type: "object",
      properties: { run_id: { type: "string" } },
      required: ["run_id"],
    },
  },
});

describe("gen-types", () => {
  it("passes when the file matches and fails after the schema gains a field", async () => {
    const file = join(mkdtempSync(join(tmpdir(), "gen-types-")), "generated.ts");
    const quiet = () => {};
    expect(await run({ check: false, schema: schema(), file })).toBe(0);
    expect(readFileSync(file, "utf8")).toContain("run_id");
    expect(await run({ check: true, schema: schema(), file, log: quiet })).toBe(0);

    const changed = schema();
    changed.$defs.RunCreated.properties.status = { type: "string" };
    const lines = [];
    expect(await run({ check: true, schema: changed, file, log: (m) => lines.push(m) })).toBe(1);
    expect(lines[0]).toContain("src/api/generated.ts is out of date");
  });
});

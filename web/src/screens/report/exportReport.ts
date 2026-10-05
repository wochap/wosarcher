// The Report screen's exports: the markdown file and the context as JSON.
import type { Context } from "../../api/generated";
import type { RunDetail } from "../../api/types";
import { recipeOf } from "../../run/format";

/** `# <query>`, a blank line, and the report. */
export const markdownFile = (query: string, report: string) => `# ${query}\n\n${report}`;

export function download(name: string, text: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

export function contextJson(detail: RunDetail, context: Context) {
  const uris = new Map(context.sources.map((s) => [s.source_id, s.uri]));
  return {
    run: detail.run_id,
    parent: detail.parent_run_id ?? null,
    query: detail.query,
    options: {
      recipe: recipeOf(detail.until, detail.writing.format),
      sources: detail.sources ?? "both",
      profile: detail.profile,
      writing: detail.writing,
    },
    passages: context.passages.map((p) => ({
      cite: p.n,
      score: p.display ?? null,
      source: uris.get(p.source_id) ?? "",
      heading_path: p.heading_path ?? [],
      text: p.text,
    })),
  };
}

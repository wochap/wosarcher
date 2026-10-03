// Citation groups in a report body (`[1]`, `[1, 2]`, as report-writing's `citations()`), the
// markdown the report renderer gets, and the chip labels per citation marker.
import type { Context, Source } from "../api/generated";
import type { WritingOptions } from "../api/types";

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\](?!\()/g;
const PARTIAL = /\[[\d,\s]*$/;
const YEAR = /\d{4}/;
const SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹";

export type CitationGroup = { start: number; end: number; numbers: number[] };

export function citationGroups(body: string): CitationGroup[] {
  return [...body.matchAll(CITATION)].map((m) => ({
    start: m.index,
    end: m.index + m[0].length,
    numbers: m[1].split(",").map((n) => Number(n.trim())),
  }));
}

/**
 * Each cited number becomes a `#cite-n` link, which the renderer turns into a chip. While
 * streaming, a trailing partial group (`[1`) is dropped and a `#caret` link is appended.
 */
export function prepare(body: string, streaming: boolean): string {
  const text = streaming ? body.replace(PARTIAL, "") : body;
  const linked = text.replace(CITATION, (_, numbers: string) =>
    numbers
      .split(",")
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(""),
  );
  return streaming ? `${linked}[](#caret)` : linked;
}

/** Web host without `www.`, or the file name; as report-writing's `site()`. */
export function site(source: Pick<Source, "kind" | "uri">): string {
  if (source.kind === "file") return source.uri.split("/").pop() ?? source.uri;
  try {
    return new URL(source.uri).hostname.replace(/^www\./, "");
  } catch {
    return source.uri;
  }
}

export function year(source: Pick<Source, "published">): string {
  return YEAR.exec(source.published ?? "")?.[0] ?? "n.d.";
}

/** The chip text of passage `n`: "[3]", "³", or "Author, Year". */
export function label(
  n: number,
  marker: WritingOptions["citation_marker"],
  context: Pick<Context, "passages" | "sources"> | null,
): string {
  if (marker === "superscript") {
    return [...String(n)].map((d) => SUP[Number(d)]).join("");
  }
  if (marker === "author-year" && context) {
    const passage = context.passages.find((p) => p.n === n);
    const source = context.sources.find((s) => s.source_id === passage?.source_id);
    if (source) return `${source.author || site(source)}, ${year(source)}`;
  }
  return `[${n}]`;
}

/** The host of a web URL without `www.`, or a file's path, as passages show their source. */
export function domain(uri: string): string {
  if (!/^https?:\/\//.test(uri)) return uri;
  return site({ kind: "web", uri });
}

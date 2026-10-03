// The Report aside: the sources with kept counts and the citations that use them, and the
// selected passages.
import type { Context } from "../../api/generated";
import type { WritingOptions } from "../../api/types";
import { domain, label } from "../../run/citations";
import type { RunView } from "../../run/reducer";
import type { FileRow } from "../../run/useRunData";
import css from "./ReportScreen.module.css";

type Props = {
  run: RunView | null;
  files: FileRow[];
  context: Context | null;
  marker: WritingOptions["citation_marker"];
};

export function SelectedPassages({ context, marker }: Pick<Props, "context" | "marker">) {
  return (
    <div className={css.passages}>
      {context?.passages.map((p) => {
        const source = context.sources.find((s) => s.source_id === p.source_id);
        return (
          <div key={p.n} className={css.passage}>
            <div className={css.passageHead}>
              <span className={css.cite}>{label(p.n, marker, context)}</span>
              <span className={css.score}>{p.display == null ? "–" : p.display.toFixed(2)}</span>
              <span className={css.heading}>{p.heading_path?.join(" › ")}</span>
            </div>
            <p className={css.passageText}>{p.text}</p>
            <span className={css.domain}>{domain(source?.uri ?? "")}</span>
          </div>
        );
      })}
    </div>
  );
}

export function ReportAside({ run, files, context, marker }: Props) {
  const web = Object.values(run?.sources ?? {}).filter((s) => s.kind === "web");
  const failed = web.filter((s) => s.state === "failed").length;
  const cites: Record<string, string[]> = {};
  for (const p of context?.passages ?? []) {
    cites[p.source_id] = [...(cites[p.source_id] ?? []), label(p.n, marker, context)];
  }
  const rows = [
    ...web
      .filter((s) => s.state !== "failed")
      .map((s) => ({ id: s.sourceId, title: s.title, uri: s.uri, href: s.uri })),
    ...files.map((f) => ({ id: f.sourceId, title: f.title, uri: f.uri, href: undefined })),
  ].sort((a, b) => (cites[b.id]?.length ?? 0) - (cites[a.id]?.length ?? 0));
  return (
    <aside className={css.aside}>
      <section>
        <h2 className={css.asideTitle}>
          Sources{" "}
          <span
            className={css.asideCount}
          >{`${rows.length}${failed ? ` · ${failed} failed` : ""}`}</span>
        </h2>
        <ol className={css.sources}>
          {rows.map((s) => (
            <li key={s.uri} className={css.source}>
              {s.href ? (
                <a className={css.sourceTitle} href={s.href} target="_blank" rel="noreferrer">
                  {s.title}
                </a>
              ) : (
                <span className={css.sourceTitle}>{s.title}</span>
              )}
              <span className={css.kept}>{cites[s.id] ? `${cites[s.id].length} kept` : ""}</span>
              <span className={css.sourceUrl}>{s.uri.replace(/^https?:\/\//, "")}</span>
              <span className={css.sourceCites}>{(cites[s.id] ?? []).join(" ")}</span>
            </li>
          ))}
        </ol>
      </section>
      <section>
        <h2 className={css.asideTitle}>
          Selected passages <span className={css.asideCount}>{context?.passages.length ?? ""}</span>
        </h2>
        <SelectedPassages context={context} marker={marker} />
      </section>
    </aside>
  );
}

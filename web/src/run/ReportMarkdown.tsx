// A report body with `[n]` markers rendered as markdown with citation chips, and a blinking
// caret at the end while it streams. `variant` picks the Live panel or Report article sizes.
import { type ComponentProps, useMemo } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Context } from "../api/generated";
import type { WritingOptions } from "../api/types";
import { HelpTip } from "../components/HelpTip";
import { label, prepare } from "./citations";
import css from "./ReportMarkdown.module.css";

export type CiteHandlers = {
  onCite: (n: number, rect: DOMRect) => void;
  onLeave: () => void;
};

type Props = CiteHandlers & {
  body: string;
  streaming?: boolean;
  marker: WritingOptions["citation_marker"];
  context: Context | null;
  variant: "live" | "article";
};

export function ReportMarkdown({
  body,
  streaming = false,
  marker,
  context,
  variant,
  onCite,
  onLeave,
}: Props) {
  // One component per marker, context, and handlers, so chips keep focus while text streams.
  const components = useMemo(
    () => ({ a: link({ marker, context, onCite, onLeave }), table: Table }),
    [marker, context, onCite, onLeave],
  );
  return (
    <div className={css.report} data-variant={variant}>
      <Markdown remarkPlugins={REMARK} components={components}>
        {prepare(body, streaming)}
      </Markdown>
    </div>
  );
}

const REMARK = [remarkGfm];

/** A GFM table in Nocturne's style, scrolling sideways inside its own area. */
function Table({ children }: ComponentProps<"table">) {
  return (
    <div className={css.tableWrap}>
      <table className="table">{children}</table>
    </div>
  );
}

function link({ marker, context, onCite, onLeave }: Omit<Props, "body" | "streaming" | "variant">) {
  return function Link({ href, children }: ComponentProps<"a">) {
    if (href === "#caret") return <span className={css.caret} aria-hidden="true" />;
    const cite = /^#cite-(\d+)$/.exec(href ?? "");
    if (cite) {
      const n = Number(cite[1]);
      const show = (e: { currentTarget: HTMLElement }) =>
        onCite(n, e.currentTarget.getBoundingClientRect());
      return (
        <button
          type="button"
          className={css.chip}
          data-marker={marker}
          aria-label={`Citation ${n}, show passage`}
          onMouseEnter={show}
          onFocus={show}
          onMouseLeave={onLeave}
          onBlur={onLeave}
        >
          {label(n, marker, context)}
        </button>
      );
    }
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  };
}

/** A report's References list under a heading naming its reference style. */
export function References({
  entries,
  style,
  variant,
}: {
  entries: string[];
  style: string;
  variant: "live" | "article";
}) {
  if (!entries.length) return null;
  return (
    <div className={css.report} data-variant={variant}>
      <h2 className={css.referencesHeading}>
        References
        <span className={css.referenceStyle}>{style}</span>
        <HelpTip help="w-ref" />
      </h2>
      <ol className={css.references}>
        {entries.map((entry) => (
          <li key={entry}>
            <Markdown components={{ p: ({ children }) => <>{children}</> }}>{entry}</Markdown>
          </li>
        ))}
      </ol>
    </div>
  );
}

// The citation tooltip: passage `n` of the run's context with its score, text, and source;
// below the chip, or above it when less than 230px remain. One fixed element per screen.
import { useCallback, useEffect, useState } from "react";
import type { Context } from "../api/generated";
import type { WritingOptions } from "../api/types";
import { useUi } from "../app/context";
import css from "./CitationTooltip.module.css";
import { domain, label } from "./citations";

export type Cite = { n: number; rect: DOMRect };

/** The shown citation; Escape hides it through the overlay stack. */
export function useCitation() {
  const { overlay } = useUi();
  const [cite, setCite] = useState<Cite | null>(null);
  const onCite = useCallback((n: number, rect: DOMRect) => setCite({ n, rect }), []);
  const onLeave = useCallback(() => setCite(null), []);
  useEffect(() => (cite ? overlay("tooltip", onLeave) : undefined), [cite, overlay, onLeave]);
  return { cite, onCite, onLeave };
}

const WIDTH = 372;
const ROOM = 230;

export function tooltipPlace(
  rect: DOMRect,
  width = window.innerWidth,
  height = window.innerHeight,
) {
  const x = Math.min(Math.max(rect.left - 20, 8), width - WIDTH);
  const below = rect.bottom + ROOM < height;
  return { left: x, top: below ? rect.bottom + 6 : rect.top - 6, above: !below };
}

type Props = {
  cite: Cite | null;
  context: Context | null;
  marker: WritingOptions["citation_marker"];
};

export function CitationTooltip({ cite, context, marker }: Props) {
  if (!cite || !context) return null;
  const passage = context.passages.find((p) => p.n === cite.n);
  if (!passage) return null;
  const source = context.sources.find((s) => s.source_id === passage.source_id);
  const place = tooltipPlace(cite.rect);
  const score = passage.display;
  return (
    <div
      role="tooltip"
      className={css.tooltip}
      data-above={place.above}
      style={{ left: place.left, top: place.top }}
    >
      <div className={css.head}>
        <span className={css.label}>{label(passage.n, marker, context)}</span>
        <span className={css.score}>{score == null ? "–" : score.toFixed(2)}</span>
        {score != null && (
          <div className={css.bar}>
            <div className={css.fill} style={{ width: `${score * 100}%` }} />
          </div>
        )}
        <span className={css.relevance}>relevance</span>
      </div>
      <p className={css.text}>“{passage.text}”</p>
      <div className={css.source}>
        <span className={css.title}>{source?.title}</span>
        <span className={css.where}>
          <span className={css.domain}>{domain(source?.uri ?? "")}</span>
          {passage.heading_path?.length ? ` · ${passage.heading_path.join(" › ")}` : ""}
        </span>
      </div>
    </div>
  );
}

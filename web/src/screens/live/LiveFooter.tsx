// Elapsed time, tokens, cost, and the event connection with its dot.
import { Timer } from "@phosphor-icons/react";
import type { Conn } from "../../api/events";
import { HelpTip } from "../../components/HelpTip";
import { fmtCost, fmtElapsed, fmtK } from "../../run/format";
import type { RunView } from "../../run/reducer";
import css from "./LiveFooter.module.css";

const CONN: Record<Conn["state"], string> = {
  connecting: "Connecting",
  connected: "Connected",
  reconnecting: "Reconnecting",
  replaying: "Replaying",
  unavailable: "Live updates unavailable",
  closed: "Closed · run ended",
};

/** A catalog run's line: the wave, nodes expanding, extracted, failed (or the stop reason). */
export type CatalogFooter = {
  wave: number;
  done: boolean;
  expanding: number;
  extracted: number;
  failed: number;
  reason?: string;
};

type Props = {
  run: RunView;
  conn: Conn;
  elapsed: number;
  isPhone: boolean;
  catalog?: CatalogFooter;
};

/** "wave 3 · 12 nodes expanding · 72 extracted · 4 failed"; done: "5 waves · … · frontier empty". */
export function catalogParts(c: CatalogFooter): { text: string; warn?: boolean; mono?: boolean }[] {
  const parts: { text: string; warn?: boolean; mono?: boolean }[] = [
    {
      text: c.done ? `${c.wave} ${c.wave === 1 ? "wave" : "waves"}` : `wave ${c.wave}`,
      mono: true,
    },
  ];
  if (!c.done) parts.push({ text: `${c.expanding} nodes expanding` });
  parts.push({ text: `${c.extracted} extracted` });
  if (c.failed) parts.push({ text: `${c.failed} failed`, warn: true });
  if (c.done && c.reason) parts.push({ text: c.reason });
  return parts;
}

export function LiveFooter({ run, conn, elapsed, isPhone, catalog }: Props) {
  return (
    <footer className={css.footer}>
      <span className={css.item}>
        <Timer aria-hidden="true" />
        {fmtElapsed(elapsed)}
      </span>
      {catalog && catalog.wave > 0 ? (
        <span className={css.catalog}>
          {catalogParts(catalog).map((p, i) => (
            <span key={p.text} className={css.catalogPart}>
              {i > 0 && <span aria-hidden="true">·</span>}
              <span className={p.mono ? css.wave : p.warn ? css.warn : undefined}>{p.text}</span>
            </span>
          ))}
        </span>
      ) : (
        !catalog && (
          <>
            <span title="Prompt / completion tokens across all stages">
              {fmtK(run.tokensIn)} in · {fmtK(run.tokensOut)} out
            </span>
            <span className={css.cost}>
              {fmtCost(run.cost)}
              <HelpTip help="tokens" />
            </span>
          </>
        )
      )}
      <span className={css.conn}>
        <span className={css.dot} data-state={conn.state} />
        {CONN[conn.state]}
        {!isPhone && <span className={css.seq}>seq {run.lastSeq}</span>}
      </span>
    </footer>
  );
}

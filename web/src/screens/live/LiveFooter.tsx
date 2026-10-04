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

type Props = { run: RunView; conn: Conn; elapsed: number; isPhone: boolean };

export function LiveFooter({ run, conn, elapsed, isPhone }: Props) {
  return (
    <footer className={css.footer}>
      <span className={css.item}>
        <Timer aria-hidden="true" />
        {fmtElapsed(elapsed)}
      </span>
      <span title="Prompt / completion tokens across all stages">
        {fmtK(run.tokensIn)} in · {fmtK(run.tokensOut)} out
      </span>
      <span className={css.cost}>
        {fmtCost(run.cost)}
        <HelpTip help="tokens" />
      </span>
      <span className={css.conn}>
        <span className={css.dot} data-state={conn.state} />
        {CONN[conn.state]}
        {!isPhone && <span className={css.seq}>seq {run.lastSeq}</span>}
      </span>
    </footer>
  );
}

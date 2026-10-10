// One banner at a time, by priority: reconnecting > unavailable > replaying > reconnected (4.5 s) >
// cancelled > connecting or queued > rewrite. A banner, never a modal: the screen stays usable.
import {
  ArrowsClockwise,
  Browser,
  CheckCircle,
  Circle,
  CircleNotch,
  HourglassMedium,
  type Icon,
  Recycle,
  StopCircle,
  TerminalWindow,
  WifiSlash,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { Conn } from "../../api/events";
import type { RunQueuedData, SlotHolder } from "../../api/types";
import { fmtElapsed } from "../../run/format";
import type { RunView } from "../../run/reducer";
import { stageLabel, stoppedAt } from "./model";
import css from "./StatusBanner.module.css";

export const RECONNECTED_MS = 4500;

/** The page's WebSocket origin, as the event stream uses it. */
export function socketOrigin(at: Location = window.location): string {
  return `${at.protocol === "https:" ? "wss" : "ws"}://${at.host}`;
}

/** True for 4.5 s after a replay finishes. */
function useReconnected(conn: Conn): boolean {
  const previous = useRef(conn.state);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const was = previous.current;
    previous.current = conn.state;
    if (was !== "replaying" || conn.state !== "connected") {
      setShown(false);
      return;
    }
    setShown(true);
    const timer = setTimeout(() => setShown(false), RECONNECTED_MS);
    return () => clearTimeout(timer);
  }, [conn.state]);
  return shown;
}

/** "Next in line.", "2nd in line.", "3rd in line.", then "<n>th in line.". */
function place(position: number): string {
  if (position === 1) return "Next in line.";
  const suffix = position === 2 ? "nd" : position === 3 ? "rd" : "th";
  return `${position}${suffix} in line.`;
}

/** Why a queued run waits, from its latest `run.queued` data; every run not from the CLI counts as web. */
export function queuedText(queued: RunQueuedData): string {
  const held = queued.held ?? [];
  const n = held.length;
  const cli = held.filter((h) => h.origin === "cli").length;
  const web = n - cli;
  const where = place(queued.position);
  if (cli === n) {
    return `Waiting for a free slot: ${n} of ${queued.limit} in use, all by CLI runs an agent started on this machine. ${where} This run starts as soon as one of them finishes or is cancelled.`;
  }
  const mix = [web && `${web} web`, cli && `${cli} CLI`].filter(Boolean).join(", ");
  return `Waiting for a free slot: ${n} of ${queued.limit} in use (${mix}). ${where}`;
}

function Holder({ holder, now }: { holder: SlotHolder; now: number }) {
  const cli = holder.origin === "cli";
  const Glyph = cli ? TerminalWindow : Browser;
  return (
    <span className={css.holder}>
      <Circle weight="fill" className={css.holderDot} aria-hidden="true" />
      <span className={css.holderId}>{holder.run_id}</span>
      <span className={css.holderOrigin}>
        <Glyph aria-hidden="true" className={css.holderIcon} />
        {cli ? "CLI" : "web"}
      </span>
      <span>· running {fmtElapsed((now - Date.parse(holder.started)) / 1000)}</span>
    </span>
  );
}

type Banner = {
  tone: "warn" | "accent" | "muted";
  icon: Icon;
  spin?: boolean;
  text: string;
  holders?: SlotHolder[];
};

type Props = { run: RunView; conn: Conn; elapsed: number; now: number; rewriteOf?: string | null };

export function StatusBanner({ run, conn, elapsed, now, rewriteOf }: Props) {
  const reconnected = useReconnected(conn);
  let banner: Banner | null = null;
  if (conn.state === "reconnecting") {
    banner = {
      tone: "warn",
      icon: WifiSlash,
      text: `Connection lost. Reconnecting (attempt ${conn.attempt})… The run continues on the server; events replay from seq ${run.lastSeq}.`,
    };
  } else if (conn.state === "unavailable") {
    banner = {
      tone: "warn",
      icon: WifiSlash,
      text: "Live updates unavailable. The server did not accept the event connection; the run continues on the server and its status is checked every 30 s.",
    };
  } else if (conn.state === "replaying") {
    banner = {
      tone: "accent",
      icon: ArrowsClockwise,
      spin: true,
      text: `Reconnected. Replaying ${conn.replayed} missed events…`,
    };
  } else if (reconnected) {
    banner = {
      tone: "accent",
      icon: CheckCircle,
      text: `Reconnected · replayed ${conn.replayed} events, nothing lost.`,
    };
  } else if (run.status === "cancelled") {
    const stage = stoppedAt(run);
    banner = {
      tone: "muted",
      icon: StopCircle,
      text: `Cancelled at ${stage ? stageLabel(stage) : "start"} after ${fmtElapsed(elapsed)}. Completed stages are kept; nothing was written.`,
    };
  } else if (run.status === "queued" && run.queued) {
    banner = {
      tone: "muted",
      icon: HourglassMedium,
      text: queuedText(run.queued),
      holders: run.queued.held ?? [],
    };
  } else if (run.status === "queued") {
    banner = {
      tone: "accent",
      icon: CircleNotch,
      spin: true,
      text: `Connecting to ${socketOrigin()}…`,
    };
  } else if (
    rewriteOf &&
    run.status === "running" &&
    ["pending", "waiting"].includes(run.phases.write.state)
  ) {
    banner = {
      tone: "accent",
      icon: Recycle,
      text: `Rewrite of ${rewriteOf}: sources and passages are reused, only the write stage runs.`,
    };
  }
  if (!banner) return null;
  const Glyph = banner.icon;
  return (
    <div role="status" className={css.banner} data-tone={banner.tone}>
      <Glyph className={`${css.icon} ${banner.spin ? "spin" : ""}`} aria-hidden="true" />
      <span className={css.text}>
        <span>{banner.text}</span>
        {banner.holders && (
          <span className={css.holders}>
            {banner.holders.map((holder) => (
              <Holder key={holder.run_id} holder={holder} now={now} />
            ))}
          </span>
        )}
      </span>
    </div>
  );
}

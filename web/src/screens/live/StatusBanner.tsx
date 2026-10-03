// One banner at a time, by priority: reconnecting > replaying > reconnected (4.5 s) >
// cancelled > connecting or queued > rewrite. A banner, never a modal: the screen stays usable.
import {
  ArrowsClockwise,
  CheckCircle,
  CircleNotch,
  type Icon,
  Recycle,
  StopCircle,
  WifiSlash,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { Conn } from "../../api/events";
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

type Banner = { tone: "warn" | "accent" | "muted"; icon: Icon; spin?: boolean; text: string };

type Props = { run: RunView; conn: Conn; elapsed: number; rewriteOf?: string | null };

export function StatusBanner({ run, conn, elapsed, rewriteOf }: Props) {
  const reconnected = useReconnected(conn);
  let banner: Banner | null = null;
  if (conn.state === "reconnecting") {
    banner = {
      tone: "warn",
      icon: WifiSlash,
      text: `Connection lost. Reconnecting (attempt ${conn.attempt})… The run continues on the server; events replay from seq ${run.lastSeq}.`,
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
  } else if (run.status === "queued") {
    const queued = run.queuePosition !== undefined ? " · queued, waiting for a free worker" : "";
    banner = {
      tone: "accent",
      icon: CircleNotch,
      spin: true,
      text: `Connecting to ${socketOrigin()}${queued}…`,
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
      <span className={css.text}>{banner.text}</span>
    </div>
  );
}

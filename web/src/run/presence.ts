// Presence for a waiting run: while the question card is shown and the user is active (pointer,
// key, or focus activity in the last 10 seconds, tab visible), `send` runs at most every 10
// seconds. After 10 idle seconds `left` counts down from the full timeout, which is what the
// server will enforce absent further presence; activity resets it and sends presence at once.
import { useEffect, useRef, useState } from "react";

export const ACTIVE_MS = 10_000;
const TICK_MS = 250;
const ACTIVITY = ["pointermove", "pointerdown", "keydown", "focus"] as const;

/** Seconds left before the run continues on its own; null while the user is active. */
export function usePresence(shown: boolean, timeout: number, send: () => void): number | null {
  const [left, setLeft] = useState<number | null>(null);
  const latest = useRef(send);
  latest.current = send;

  useEffect(() => {
    if (!shown) {
      setLeft(null);
      return;
    }
    const start = Date.now();
    let activeAt = start;
    let sentAt = start;
    let idleAt: number | null = null;
    latest.current();

    const present = (now: number) => {
      if (now - sentAt < ACTIVE_MS) return;
      sentAt = now;
      latest.current();
    };
    const activity = () => {
      if (document.hidden) return;
      const now = Date.now();
      activeAt = now;
      if (idleAt !== null) {
        idleAt = null;
        setLeft(null);
      }
      present(now);
    };
    const tick = () => {
      const now = Date.now();
      if (!document.hidden && now - activeAt < ACTIVE_MS) return present(now);
      idleAt ??= now;
      setLeft(Math.max(0, timeout - (now - idleAt) / 1000));
    };

    for (const type of ACTIVITY) window.addEventListener(type, activity, true);
    document.addEventListener("visibilitychange", activity);
    const timer = setInterval(tick, TICK_MS);
    return () => {
      clearInterval(timer);
      for (const type of ACTIVITY) window.removeEventListener(type, activity, true);
      document.removeEventListener("visibilitychange", activity);
    };
  }, [shown, timeout]);

  return left;
}

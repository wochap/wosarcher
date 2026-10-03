// Global shortcuts: Alt+1..4 switch screens (by physical key), Escape closes the top overlay,
// `/` focuses the History search. Nothing acts while the sign-in screen is shown.
import { useEffect, useRef } from "react";
import type { OverlayKind } from "./context";
import type { Screen } from "./route";

const SCREENS: Screen[] = ["new", "live", "history", "settings"];
const PRIORITY: OverlayKind[] = ["alertdialog", "dialog", "tooltip"];

export type Overlay = { kind: OverlayKind; close: () => void };

/** The overlay Escape closes: alert dialogs first, then form dialogs, then tooltips. */
export function topOverlay(open: Overlay[]): Overlay | undefined {
  for (const kind of PRIORITY) {
    const match = open.filter((o) => o.kind === kind).at(-1);
    if (match) return match;
  }
  return undefined;
}

export const SEARCH_ID = "history-search";

function typing(target: EventTarget | null): boolean {
  const tag = (target as HTMLElement | null)?.tagName ?? "";
  return /^(INPUT|TEXTAREA|SELECT)$/.test(tag);
}

export type KeyContext = {
  locked: boolean;
  screen: string;
  goTo(screen: Screen): void;
  overlays(): Overlay[];
};

export function handleKey(e: KeyboardEvent, ctx: KeyContext) {
  if (ctx.locked) return;
  const digit = /^Digit([1-4])$/.exec(e.code);
  if (e.altKey && digit) {
    e.preventDefault();
    ctx.goTo(SCREENS[Number(digit[1]) - 1]);
    return;
  }
  if (e.key === "Escape") {
    topOverlay(ctx.overlays())?.close();
    return;
  }
  if (e.key === "/" && ctx.screen === "history" && !typing(e.target)) {
    e.preventDefault();
    document.getElementById(SEARCH_ID)?.focus();
  }
}

export function useKeys(ctx: KeyContext) {
  const latest = useRef(ctx);
  latest.current = ctx;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => handleKey(e, latest.current);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

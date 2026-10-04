// Inline help: the `?` button after a label, and the one tooltip the app shows for it.
// Hover or focus opens the tooltip, leaving closes it after 140 ms, a click pins it.
import { Question } from "@phosphor-icons/react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { type HelpState, type HelpUi, useHelp } from "../app/context";
import css from "./HelpTip.module.css";
import { helpFor } from "./help";
import { placeHelp } from "./helpPlacement";

export const HELP_TOOLTIP_ID = "help-tooltip";
const CLOSE_MS = 140;

type Props = {
  /** A key of `HELP`, or a composed `wait-<phase>` / `retry-<stage>` key. */
  help: string;
  /** The accessible label after "Help: "; defaults to the entry's title. */
  label?: string;
};

export function HelpTip({ help: key, label }: Props) {
  const ui = useHelp();
  const owner = useId();
  const open = ui?.help?.owner === owner;
  const pinned = open && !!ui?.help?.pinned;
  const show = (el: HTMLElement, pin: boolean) =>
    ui?.openHelp({ key, owner, rect: el.getBoundingClientRect(), pinned: pin });
  const hover = (el: HTMLElement) => {
    if (!ui?.help?.pinned) show(el, false);
  };
  return (
    <button
      type="button"
      className={css.button}
      data-help={key}
      data-pinned={pinned || undefined}
      aria-label={`Help: ${label ?? helpFor(key).title}`}
      aria-describedby={HELP_TOOLTIP_ID}
      onMouseEnter={(e) => hover(e.currentTarget)}
      onFocus={(e) => hover(e.currentTarget)}
      onMouseLeave={() => ui?.leaveHelp()}
      onBlur={() => ui?.leaveHelp()}
      onClick={(e) => {
        if (pinned) ui?.closeHelp();
        else show(e.currentTarget, true);
      }}
    >
      <Question aria-hidden="true" />
    </button>
  );
}

/** The help state `App` provides; Escape closes it first through the overlay stack. */
export function useHelpState(overlay: (kind: "help", close: () => void) => () => void): HelpUi {
  const [help, setHelp] = useState<HelpState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const keepHelp = useCallback(() => clearTimeout(timer.current), []);
  const closeHelp = useCallback(() => {
    clearTimeout(timer.current);
    setHelp(null);
  }, []);
  const openHelp = useCallback((next: HelpState) => {
    clearTimeout(timer.current);
    setHelp(next);
  }, []);
  const leaveHelp = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setHelp((h) => (h?.pinned ? h : null)), CLOSE_MS);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  const isOpen = !!help;
  useEffect(() => (isOpen ? overlay("help", closeHelp) : undefined), [isOpen, overlay, closeHelp]);
  useEffect(() => {
    if (!isOpen) return;
    const onPress = (e: PointerEvent) => {
      const target = e.target as Element | null;
      if (!target?.closest?.(`[data-help], #${HELP_TOOLTIP_ID}`)) closeHelp();
    };
    document.addEventListener("pointerdown", onPress);
    document.addEventListener("scroll", closeHelp, true);
    return () => {
      document.removeEventListener("pointerdown", onPress);
      document.removeEventListener("scroll", closeHelp, true);
    };
  }, [isOpen, closeHelp]);
  return useMemo(
    () => ({ help, openHelp, closeHelp, leaveHelp, keepHelp }),
    [help, openHelp, closeHelp, leaveHelp, keepHelp],
  );
}

export function HelpPopover() {
  const ui = useHelp();
  const help = ui?.help;
  if (!ui || !help) return null;
  const entry = helpFor(help.key);
  const place = placeHelp(help.rect, { width: window.innerWidth, height: window.innerHeight });
  return (
    <div
      id={HELP_TOOLTIP_ID}
      role="tooltip"
      className={css.tooltip}
      data-below={place.below}
      style={{ left: place.x, top: place.y }}
      onMouseEnter={ui.keepHelp}
      onMouseLeave={() => {
        if (!help.pinned) ui.leaveHelp();
      }}
    >
      <span aria-hidden="true" className={css.arrow} style={{ left: place.arrowX }} />
      <span className={css.title}>{entry.title}</span>
      <span className={css.body}>{entry.body}</span>
      {entry.example && (
        <span className={css.example}>
          Example: <span className={css.exampleText}>{entry.example}</span>
        </span>
      )}
    </div>
  );
}

// Where the help tooltip goes: centred on its button, 8px inside the viewport, below the
// button unless less than 180px remain below and at least 180px above, as the prototype.
export const HELP_WIDTH = 272;
const MARGIN = 8;
const ROOM = 180;
const GAP = 9;

type Rect = Pick<DOMRect, "left" | "top" | "bottom" | "width">;
export type HelpPlace = { x: number; y: number; below: boolean; arrowX: number };

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(n, hi));

export function placeHelp(rect: Rect, viewport: { width: number; height: number }): HelpPlace {
  const cx = rect.left + rect.width / 2;
  const x = clamp(cx - HELP_WIDTH / 2, MARGIN, viewport.width - MARGIN - HELP_WIDTH);
  const below = rect.bottom + ROOM < viewport.height || rect.top < ROOM;
  return {
    x,
    y: below ? rect.bottom + GAP : rect.top - GAP,
    below,
    arrowX: clamp(cx - x - 5, 10, HELP_WIDTH - 20),
  };
}

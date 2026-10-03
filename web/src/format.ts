// Display formats shared by the screens.

/** 125 → "2:05". */
export function minSec(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

const DATE = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
const TIME = new Intl.DateTimeFormat("en-US", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** "Oct 3, 09:12", as the prototype's dates. */
export function dateTime(iso: string): string {
  const d = new Date(iso);
  return `${DATE.format(d)}, ${TIME.format(d)}`;
}

/** "Oct 3". */
export function shortDate(iso: string): string {
  return DATE.format(new Date(iso));
}

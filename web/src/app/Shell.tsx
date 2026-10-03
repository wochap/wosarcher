// The frame around every screen: the desktop sidebar, or the phone top bar below 720px.
import {
  ClockCounterClockwise,
  FunnelSimple,
  GearSix,
  type Icon,
  Moon,
  PlusCircle,
  Pulse,
  Sun,
} from "@phosphor-icons/react";
import { type ReactNode, useEffect, useState } from "react";
import { useUi } from "./context";
import type { Screen } from "./route";
import css from "./Shell.module.css";

const PHONE_QUERY = "(max-width: 719.98px)";

const phoneMedia = () => window.matchMedia?.(PHONE_QUERY);

export function useIsPhone(): boolean {
  const [phone, setPhone] = useState(() => phoneMedia()?.matches ?? false);
  useEffect(() => {
    const media = phoneMedia();
    if (!media) return;
    const update = () => setPhone(media.matches);
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  return phone;
}

type Item = { screen: Screen; label: string; icon: Icon; hint: string };
const ITEMS: Item[] = [
  { screen: "new", label: "New run", icon: PlusCircle, hint: "Alt 1" },
  { screen: "live", label: "Live run", icon: Pulse, hint: "Alt 2" },
  { screen: "history", label: "History", icon: ClockCounterClockwise, hint: "Alt 3" },
  { screen: "settings", label: "Settings", icon: GearSix, hint: "Alt 4" },
];

type Props = {
  screen: Screen;
  liveDot: boolean;
  onGo: (screen: Screen) => void;
  /** Rendered over the whole frame: sign-in, toast. */
  overlays?: ReactNode;
  children: ReactNode;
};

export function socketOrigin(at: Location = window.location): string {
  return `${at.protocol === "https:" ? "wss" : "ws"}://${at.host}`;
}

export function Shell({ screen, liveDot, onGo, overlays, children }: Props) {
  const { theme, toggleTheme, isPhone, healthWarn } = useUi();
  const ThemeIcon = theme === "dark" ? Sun : Moon;
  const themeLabel = theme === "dark" ? "Light theme" : "Dark theme";
  const items = ITEMS.map((item) => {
    const active = screen === item.screen || (item.screen === "live" && screen === "report");
    const tone =
      item.screen === "live" && liveDot
        ? "live"
        : item.screen === "settings" && healthWarn
          ? "warn"
          : null;
    return { ...item, active, tone };
  });

  const nav = isPhone ? (
    <nav aria-label="Main" className={css.top}>
      <FunnelSimple className={css.topIcon} aria-hidden="true" />
      <span className={css.topName}>wosarcher</span>
      {items.map(({ screen: id, label, icon: Glyph, active, tone }) => (
        <button
          key={id}
          type="button"
          className={css.phoneItem}
          aria-label={label}
          aria-current={active ? "page" : undefined}
          onClick={() => onGo(id)}
        >
          <Glyph className={css.itemIcon} aria-hidden="true" />
          {tone && <span className={css.dot} data-tone={tone} />}
        </button>
      ))}
      <button
        type="button"
        className={css.phoneTheme}
        aria-label={themeLabel}
        onClick={toggleTheme}
      >
        <ThemeIcon aria-hidden="true" />
      </button>
    </nav>
  ) : (
    <nav aria-label="Main" className={css.side}>
      <div className={css.brand}>
        <FunnelSimple className={css.brandIcon} aria-hidden="true" />
        <span className={css.brandName}>wosarcher</span>
      </div>
      {items.map(({ screen: id, label, icon: Glyph, hint, active, tone }) => (
        <button
          key={id}
          type="button"
          className={css.item}
          aria-current={active ? "page" : undefined}
          onClick={() => onGo(id)}
        >
          <Glyph className={css.itemIcon} aria-hidden="true" />
          <span className={css.itemLabel}>{label}</span>
          {tone && <span className={css.dot} data-tone={tone} />}
          <span className={css.hint}>{hint}</span>
        </button>
      ))}
      <div className={css.foot}>
        <button
          type="button"
          className={`btn btn-secondary ${css.themeButton}`}
          onClick={toggleTheme}
        >
          <ThemeIcon aria-hidden="true" />
          {themeLabel}
        </button>
        <div className={css.origin}>{socketOrigin()}</div>
      </div>
    </nav>
  );

  return (
    <div className={css.app} data-phone={isPhone}>
      {nav}
      <main className={css.main}>{children}</main>
      {overlays}
    </div>
  );
}

// Dark or light, set as `data-theme` on <html>. The first visit follows prefers-color-scheme;
// a choice is remembered under `wosarcher-theme`.
import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";
export const THEME_KEY = "wosarcher-theme";

export function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch {}
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState(initialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch {}
      return next;
    });
  }, []);
  return [theme, toggle];
}

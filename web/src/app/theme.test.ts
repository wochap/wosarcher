import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { initialTheme, THEME_KEY, useTheme } from "./theme";

function prefers(light: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: light && query.includes("light") }));
}

afterEach(() => vi.unstubAllGlobals());

describe("theme", () => {
  it("follows a light browser on the first visit", () => {
    prefers(true);
    expect(initialTheme()).toBe("light");
  });

  it("uses and remembers the choice", () => {
    prefers(true);
    const { result } = renderHook(() => useTheme());
    expect(document.documentElement.dataset.theme).toBe("light");
    act(() => result.current[1]());
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(initialTheme()).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("works when storage is blocked", () => {
    prefers(false);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useTheme());
    expect(result.current[0]).toBe("dark");
    act(() => result.current[1]());
    expect(result.current[0]).toBe("light");
    vi.restoreAllMocks();
  });
});

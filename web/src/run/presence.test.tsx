import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePresence } from "./presence";

const advance = (ms: number) =>
  act(() => {
    vi.advanceTimersByTime(ms);
  });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("usePresence", () => {
  it("sends presence when shown and then at most every 10 seconds while active", () => {
    const send = vi.fn();
    renderHook(() => usePresence(true, 60, send));
    expect(send).toHaveBeenCalledTimes(1);
    // Activity every second: one message per 10 seconds.
    for (let i = 0; i < 25; i++) {
      advance(1000);
      act(() => {
        window.dispatchEvent(new Event("pointermove"));
      });
    }
    expect(send).toHaveBeenCalledTimes(3);
  });

  it("counts down from the full timeout after 10 idle seconds and sends nothing", () => {
    const send = vi.fn();
    const { result } = renderHook(() => usePresence(true, 60, send));
    expect(result.current).toBeNull();
    advance(9000);
    expect(result.current).toBeNull();
    advance(1500);
    expect(Math.ceil(result.current ?? -1)).toBe(60);
    advance(13_000);
    expect(Math.ceil(result.current ?? -1)).toBe(47);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("goes back to waiting on activity, sends presence, and restarts from the full timeout", () => {
    const send = vi.fn();
    const { result } = renderHook(() => usePresence(true, 60, send));
    advance(24_000);
    expect(result.current).not.toBeNull();
    act(() => {
      window.dispatchEvent(new Event("keydown"));
    });
    expect(result.current).toBeNull();
    expect(send).toHaveBeenCalledTimes(2);
    advance(10_000);
    expect(Math.ceil(result.current ?? -1)).toBe(60);
  });

  it("treats a hidden tab as away", () => {
    const send = vi.fn();
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    const { result } = renderHook(() => usePresence(true, 30, send));
    advance(500);
    expect(result.current).not.toBeNull();
    hidden.mockRestore();
  });

  it("does nothing while the card is not shown", () => {
    const send = vi.fn();
    const { result } = renderHook(() => usePresence(false, 60, send));
    advance(30_000);
    expect(send).not.toHaveBeenCalled();
    expect(result.current).toBeNull();
  });
});

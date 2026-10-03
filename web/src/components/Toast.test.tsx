import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Toast, useToastState } from "./Toast";

let api: ReturnType<typeof useToastState>;
function Harness() {
  api = useToastState();
  return <Toast shown={api.shown} dismiss={api.dismiss} />;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("Toast", () => {
  it("shows for 2.2 s", () => {
    render(<Harness />);
    act(() => api.toast("Markdown copied"));
    expect(screen.getByRole("status").textContent).toBe("Markdown copied");
    act(() => vi.advanceTimersByTime(2100));
    expect(screen.queryByRole("status")).toBeTruthy();
    act(() => vi.advanceTimersByTime(200));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows for 6 s with Undo, which calls back and closes", () => {
    const undo = vi.fn();
    render(<Harness />);
    act(() => api.toast("Run deleted", { undo }));
    act(() => vi.advanceTimersByTime(5000));
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(undo).toHaveBeenCalledOnce();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("replaces the current toast", () => {
    render(<Harness />);
    act(() => api.toast("first"));
    act(() => vi.advanceTimersByTime(2000));
    act(() => api.toast("second"));
    expect(screen.getAllByRole("status").map((s) => s.textContent)).toEqual(["second"]);
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole("status").textContent).toBe("second");
  });
});

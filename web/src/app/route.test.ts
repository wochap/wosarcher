import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { go, parseRoute, routeHash, useRoute } from "./route";

describe("route", () => {
  it("parses every route", () => {
    expect(parseRoute("#/new")).toEqual({ screen: "new" });
    expect(parseRoute("#/live")).toEqual({ screen: "live" });
    expect(parseRoute("#/live/r_8c21")).toEqual({ screen: "live", runId: "r_8c21" });
    expect(parseRoute("#/runs/r_8c21")).toEqual({ screen: "report", runId: "r_8c21" });
    expect(parseRoute("#/history")).toEqual({ screen: "history" });
    expect(parseRoute("#/settings")).toEqual({ screen: "settings" });
    expect(parseRoute("#/preview/login")).toEqual({ screen: "preview", name: "login" });
  });

  it("sends empty and unknown fragments to #/new", () => {
    expect(parseRoute("")).toEqual({ screen: "new" });
    expect(parseRoute("#/nope")).toEqual({ screen: "new" });
    expect(parseRoute("#/runs")).toEqual({ screen: "new" });
  });

  it("round-trips through routeHash", () => {
    for (const hash of ["#/new", "#/live", "#/live/r1", "#/runs/r1", "#/history", "#/settings"]) {
      expect(routeHash(parseRoute(hash))).toBe(hash);
    }
  });

  it("keeps the screen on reload and follows hash changes", async () => {
    window.location.hash = "#/history";
    const { result, unmount } = renderHook(() => useRoute());
    expect(result.current).toEqual({ screen: "history" });
    unmount();
    const reloaded = renderHook(() => useRoute());
    expect(reloaded.result.current).toEqual({ screen: "history" });
    await act(async () => {
      go({ screen: "settings" });
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(reloaded.result.current).toEqual({ screen: "settings" });
  });
});

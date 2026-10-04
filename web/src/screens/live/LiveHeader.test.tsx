import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RunEvent } from "../../api/types";
import { ev } from "../../test/events";
import { cancelled } from "../../test/fixtures/cancelled";
import { failure } from "../../test/fixtures/failure";
import { live } from "../../test/fixtures/live";
import { loading } from "../../test/fixtures/loading";
import { RUN_ID, upTo } from "../../test/fixtures/sample";
import { viewOf } from "../../test/views";
import { deviceLabel } from "./DeviceChip";
import { LiveHeader } from "./LiveHeader";

const all = live.data.events?.[RUN_ID] as RunEvent[];
const at = (match: (e: RunEvent) => boolean) => viewOf(upTo(all, match), RUN_ID);

function header(events: RunEvent[], isPhone = false) {
  const handlers = { onCancel: vi.fn(), onOpenReport: vi.fn(), onRerun: vi.fn() };
  render(
    <LiveHeader
      run={viewOf(events, RUN_ID)}
      detail={null}
      files={2}
      isPhone={isPhone}
      cancelling={false}
      {...handlers}
    />,
  );
  return handlers;
}

const buttons = () =>
  screen
    .queryAllByRole("button")
    .filter((b) => !b.dataset.help)
    .map((b) => b.textContent);

describe("LiveHeader", () => {
  it("shows Connecting with Cancel while queued", () => {
    header(loading.data.events?.[RUN_ID] as RunEvent[]);
    expect(screen.getByText("Connecting")).toBeTruthy();
    expect(buttons()).toEqual(["Cancel"]);
  });

  it("shows Running, the meta, the query, and the device chip", () => {
    const handlers = header(upTo(all, (e) => e.type === "passages.scored"));
    expect(screen.getByText("Running")).toBeTruthy();
    expect(screen.getByText("report · both · low-vram · 2 files")).toBeTruthy();
    expect(screen.getByText(/How do speculative decoding/)).toBeTruthy();
    expect(screen.getByText("desktop:gpu0")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(handlers.onCancel).toHaveBeenCalled();
  });

  it("hides the device chip on phones", () => {
    header(
      upTo(all, (e) => e.type === "passages.scored"),
      true,
    );
    expect(screen.queryByText("desktop:gpu0")).toBeNull();
  });

  it("offers Open report when completed", () => {
    const handlers = header(all);
    expect(screen.getByText("Completed")).toBeTruthy();
    expect(buttons()).toEqual(["Open report"]);
    fireEvent.click(screen.getByRole("button", { name: "Open report" }));
    expect(handlers.onOpenReport).toHaveBeenCalled();
  });

  it("offers Rerun when failed or cancelled", () => {
    header(failure.data.events?.[RUN_ID] as RunEvent[]);
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(buttons()).toEqual(["Rerun"]);
  });

  it("has the Rerun help when failed", () => {
    header(failure.data.events?.[RUN_ID] as RunEvent[]);
    expect(screen.getByRole("button", { name: "Help: Rerun" })).toBeTruthy();
  });

  it("offers Rerun when cancelled", () => {
    header(cancelled.data.events?.[RUN_ID] as RunEvent[]);
    expect(screen.getByText("Cancelled")).toBeTruthy();
    expect(buttons()).toEqual(["Rerun"]);
  });
});

describe("deviceLabel", () => {
  it("names the running stage, a wait, or idle, without memory figures", () => {
    expect(deviceLabel(at((e) => e.type === "passages.scored"))).toEqual({
      text: "desktop:gpu0",
      tone: "busy",
    });
    const waiting = at((e) => e.type === "stage.started" && e.stage === "score");
    expect(deviceLabel(waiting)).toEqual({ text: "desktop:gpu0 · waiting", tone: "wait" });
    const idle = at((e) => e.type === "stage.started" && e.stage === "select");
    expect(deviceLabel(idle)).toEqual({ text: "desktop:gpu0", tone: "idle" });
    expect(deviceLabel(viewOf([ev(1, "run.started", {} as never, null, RUN_ID)]))).toBeNull();
  });
});

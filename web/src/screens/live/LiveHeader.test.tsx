import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { RunDetail, RunEvent } from "../../api/types";
import { ev } from "../../test/events";
import { cancelled } from "../../test/fixtures/cancelled";
import { failure } from "../../test/fixtures/failure";
import { live } from "../../test/fixtures/live";
import { loading } from "../../test/fixtures/loading";
import { RUN_ID, summary, upTo } from "../../test/fixtures/sample";
import { viewOf } from "../../test/views";
import { deviceLabel } from "./DeviceChip";
import { LiveHeader } from "./LiveHeader";

const all = live.data.events?.[RUN_ID] as RunEvent[];
const at = (match: (e: RunEvent) => boolean) => viewOf(upTo(all, match), RUN_ID);

function header(events: RunEvent[], isPhone = false, detail: RunDetail | null = null) {
  const handlers = { onCancel: vi.fn(), onOpenReport: vi.fn(), onRerun: vi.fn() };
  render(
    <LiveHeader
      run={viewOf(events, RUN_ID)}
      detail={detail}
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

/** A run whose query has `n` characters, with a Markdown heading and a line break. */
const asking = (n: number) => {
  const query = `# Brief\n**bold** ${"x".repeat(n - 17)}`;
  const start = ev(1, "run.started", {
    query,
    profile: "p",
    parent_run_id: null,
    version: 1,
    until: null,
  });
  return { query, events: [{ ...start, run_id: RUN_ID }] };
};

describe("LiveHeader", () => {
  it("clamps a long question and toggles the whole of it", () => {
    const { query, events } = asking(4030);
    header(events);
    const shown = document.getElementById("run-q") as HTMLElement;
    expect(shown.textContent).toBe(query);
    const toggle = screen.getByRole("button", { name: /Show full question/ });
    expect(toggle.textContent).toBe("Show full question· 4,030 characters");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("aria-controls")).toBe("run-q");
    fireEvent.click(toggle);
    expect(toggle.textContent).toBe("Show less· 4,030 characters");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const full = document.getElementById("run-q") as HTMLElement;
    expect(full.textContent).toBe(query);
    expect(full.querySelector("h1, strong")).toBeNull();
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("shows no toggle for a short question", () => {
    header(asking(120).events);
    expect(screen.queryByRole("button", { name: /Show full question/ })).toBeNull();
  });

  it("shows the origin label after the depth tag for CLI and API runs", () => {
    const events = upTo(all, (e) => e.type === "stage.started");
    header(events, false, { ...summary({ origin: "cli" }), last_seq: 1 } as RunDetail);
    const cli = screen.getByTitle("Started from the wosarcher CLI on this machine");
    expect(cli.textContent).toBe("cli");
    cleanup();
    header(events, false, {
      ...summary({ origin: "api", token_name: "ci-runner" }),
      last_seq: 1,
    } as RunDetail);
    expect(screen.getByTitle("Started through the API with token “ci-runner”").textContent).toBe(
      "api · ci-runner",
    );
    cleanup();
    header(events, false, { ...summary({ origin: "web" }), last_seq: 1 } as RunDetail);
    expect(screen.queryByTitle(/^Started/)).toBeNull();
  });

  it("shows Queued without a pulse once run.queued arrives", () => {
    const queued = ev(0, "run.queued", { position: 1, limit: 1, held: [] });
    header([{ ...queued, run_id: RUN_ID }]);
    const tag = screen.getByText("Queued");
    expect(tag.dataset.queued).toBe("true");
  });

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

describe("LiveHeader recipe", () => {
  it("names an answer run's recipe in the meta", () => {
    const detail = {
      ...summary({ writing: { ...summary().writing, format: "answer" } }),
      last_seq: 0,
    };
    header(
      upTo(all, (e) => e.type === "passages.scored"),
      false,
      detail,
    );
    expect(screen.getByText("answer · both · low-vram · 2 files")).toBeTruthy();
  });

  it("shows context when the run stops at select, whatever its format", () => {
    const detail = {
      ...summary({ until: "select", writing: { ...summary().writing, format: "answer" } }),
      last_seq: 0,
    };
    header(
      upTo(all, (e) => e.type === "passages.scored"),
      false,
      detail,
    );
    expect(screen.getByText("context · both · low-vram · 2 files")).toBeTruthy();
  });
});

describe("LiveHeader depth tag", () => {
  it("shows the depth after the status, Standard when the run has none", () => {
    header(all, false, { ...summary({ depth: "quick" }), last_seq: 0 });
    expect(screen.getByText("Quick")).toBeTruthy();
  });

  it("reads Standard for an older run", () => {
    header(all);
    expect(screen.getByText("Standard")).toBeTruthy();
  });
});

describe("LiveHeader thinking tags", () => {
  it("shows a tag per thinking step", () => {
    const reasoning = { plan: "none", gap: "low", write: "high" } as const;
    header(all, false, { ...summary({ reasoning }), last_seq: 0 });
    expect(screen.getByText("Gap thinking low")).toBeTruthy();
    expect(screen.getByText("Write thinking high")).toBeTruthy();
  });

  it("shows none when every step is none", () => {
    header(all);
    expect(screen.queryByText(/thinking/)).toBeNull();
  });
});

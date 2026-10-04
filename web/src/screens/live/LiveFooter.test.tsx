import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Conn } from "../../api/events";
import type { RunEvent } from "../../api/types";
import { live } from "../../test/fixtures/live";
import { RUN_ID, upTo } from "../../test/fixtures/sample";
import { openScenario } from "../../test/scenario";
import { viewOf } from "../../test/views";
import { LiveFooter } from "./LiveFooter";
import { RECONNECTED_MS, StatusBanner } from "./StatusBanner";

const all = live.data.events?.[RUN_ID] as RunEvent[];
const conn = (state: Conn["state"], attempt = 0, replayed = 0): Conn => ({
  state,
  attempt,
  replayed,
  notFound: false,
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("LiveFooter", () => {
  it("shows elapsed time, tokens, a local cost, the connection, and seq", () => {
    const run = viewOf(all, RUN_ID);
    render(<LiveFooter run={run} conn={conn("closed")} elapsed={150} isPhone={false} />);
    expect(screen.getByText("2:30")).toBeTruthy();
    expect(screen.getByText("46.5k in · 532 out")).toBeTruthy();
    expect(screen.getByText("$0.0000 · local")).toBeTruthy();
    expect(screen.getByText("Closed · run ended")).toBeTruthy();
    expect(screen.getByText(`seq ${run.lastSeq}`)).toBeTruthy();
  });

  it("shows a paid cost and hides seq on phones", () => {
    const run = { ...viewOf(all, RUN_ID), cost: 0.0024 };
    render(<LiveFooter run={run} conn={conn("connected")} elapsed={0} isPhone />);
    expect(screen.getByText("$0.0024")).toBeTruthy();
    expect(screen.getByText("Connected")).toBeTruthy();
    expect(screen.queryByText(/^seq/)).toBeNull();
  });

  it("shows live updates unavailable with a static warn dot", () => {
    const run = viewOf(all, RUN_ID);
    const { container } = render(
      <LiveFooter run={run} conn={conn("unavailable", 4)} elapsed={0} isPhone={false} />,
    );
    expect(screen.getByText("Live updates unavailable")).toBeTruthy();
    expect(container.querySelector('[data-state="unavailable"]')).toBeTruthy();
  });
});

describe("StatusBanner", () => {
  it("walks through the reconnect sequence and hides 4.5 s after the replay", () => {
    vi.useFakeTimers();
    const run = {
      ...viewOf(
        upTo(all, (e) => e.type === "stage.started" && e.stage === "chunk"),
        RUN_ID,
      ),
      lastSeq: 351,
    };
    const banner = (c: Conn) => <StatusBanner run={run} conn={c} elapsed={30} />;
    const { rerender, container } = render(banner(conn("connected")));
    expect(container.textContent).toBe("");
    rerender(banner(conn("reconnecting", 1)));
    expect(screen.getByRole("status").textContent).toBe(
      "Connection lost. Reconnecting (attempt 1)… The run continues on the server; events replay from seq 351.",
    );
    rerender(banner(conn("reconnecting", 2)));
    expect(screen.getByRole("status").textContent).toContain("attempt 2");
    rerender(banner(conn("replaying", 0, 54)));
    expect(screen.getByRole("status").textContent).toBe("Reconnected. Replaying 54 missed events…");
    rerender(banner(conn("connected", 0, 54)));
    expect(screen.getByRole("status").textContent).toBe(
      "Reconnected · replayed 54 events, nothing lost.",
    );
    act(() => vi.advanceTimersByTime(RECONNECTED_MS - 100));
    expect(screen.getByRole("status")).toBeTruthy();
    act(() => vi.advanceTimersByTime(200));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("names the queue and the page's socket origin while queued", () => {
    const run = viewOf(
      [{ seq: 0, type: "run.queued", data: { position: 1 }, run_id: RUN_ID, ts: "", stage: null }],
      RUN_ID,
    );
    render(<StatusBanner run={run} conn={conn("connected")} elapsed={0} />);
    expect(screen.getByRole("status").textContent).toBe(
      `Connecting to ws://${window.location.host} · queued, waiting for a free worker…`,
    );
  });

  it("explains a rewrite until writing starts", () => {
    const run = viewOf(
      upTo(all, (e) => e.type === "stage.started" && e.stage === "plan"),
      RUN_ID,
    );
    render(<StatusBanner run={run} conn={conn("connected")} elapsed={0} rewriteOf="r_8c21" />);
    expect(screen.getByRole("status").textContent).toBe(
      "Rewrite of r_8c21: sources and passages are reused, only the write stage runs.",
    );
  });
});

describe("PhoneTabs", () => {
  it("shows one panel at a time below 720px", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("max-width"),
      addEventListener() {},
      removeEventListener() {},
    }));
    await openScenario(live);
    const tab = (name: RegExp) => screen.getByRole("tab", { name });
    expect(tab(/Progress/).getAttribute("aria-selected")).toBe("true");
    expect(tab(/Passages/).textContent).toBe("Passages14");
    expect(screen.getByRole("region", { name: "Sub-queries" })).toBeTruthy();
    fireEvent.click(tab(/Passages/));
    expect(tab(/Passages/).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("region", { name: "Passages" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Sub-queries" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Report" })).toBeNull();
    expect(screen.queryByRole("list", { name: "Phases" })).toBeNull();
  });
});

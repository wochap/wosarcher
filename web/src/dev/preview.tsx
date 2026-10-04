// Development only: #/preview/<name> renders the app on fake data, for the side-by-side
// comparison with the prototype's scenarios. main.tsx imports this module only when
// import.meta.env.DEV, so production builds leave it out.
import { useEffect, useState } from "react";
import type { SocketFactory } from "../api/events";
import type { RunEvent } from "../api/types";
import { App } from "../app/App";
import { routeHash, type Screen } from "../app/route";
import type { LoginState } from "../screens/login/LoginScreen";
import { type FakeData, fakeApi } from "../test/fakeApi";
import { cancelled } from "../test/fixtures/cancelled";
import { failure } from "../test/fixtures/failure";
import { finished } from "../test/fixtures/finished";
import { live } from "../test/fixtures/live";
import { loading } from "../test/fixtures/loading";
import { reconnecting } from "../test/fixtures/reconnecting";
import { type Fixture, otherRuns, sourceViews, TRUNCATED_SOURCE } from "../test/fixtures/sample";
import { versions } from "../test/fixtures/versions";

type Scenario = {
  screen: Screen;
  runId?: string;
  data?: Partial<FakeData>;
  login?: () => LoginState;
  stream?: Fixture["stream"];
  dropAt?: number;
  /** Every socket closes 1006 without opening, as behind a proxy that refuses the upgrade. */
  refuse?: boolean;
  /**
   * Opens the Source dialog from the first passage card. The dialog shows this source instead
   * of the card's (`loading` never answers).
   */
  source?: string;
};

const SCENARIOS: Record<string, Scenario> = {
  login: { screen: "new", login: () => ({ kind: "idle" }) },
  "login-wrong": { screen: "new", login: () => ({ kind: "wrong", attemptsLeft: 3 }) },
  "login-limited": {
    screen: "new",
    login: () => ({ kind: "limited", until: Date.now() + 30_000, total: 30 }),
  },
  history: { screen: "history" },
  emptyHistory: { screen: "history", data: { runs: [] } },
  settings: { screen: "settings" },
  new: { screen: "new" },
  empty: { screen: "live", data: { runs: otherRuns } },
  live,
  loading,
  reconnecting,
  failure,
  cancelled,
  finished,
  versions,
  unavailable: { ...live, stream: undefined, refuse: true },
  notFound: { screen: "live", runId: "r_deleted", data: { runs: otherRuns } },
  source: { ...live, stream: undefined, source: "s11" },
  "source-loading": { ...live, stream: undefined, source: "loading" },
  "source-truncated": { ...live, stream: undefined, source: TRUNCATED_SOURCE },
  "source-file": { ...live, stream: undefined, source: "f1" },
};

/** Clicks the first passage card once the Passages panel lists it. */
function useOpenSource(scenario: Scenario | undefined) {
  useEffect(() => {
    if (!scenario?.source) return;
    const timer = setInterval(() => {
      const card = document.querySelector<HTMLButtonElement>('button[aria-label$="Open source"]');
      if (!card) return;
      clearInterval(timer);
      card.click();
    }, 100);
    return () => clearInterval(timer);
  }, [scenario]);
}

const TERMINAL = new Set(["run.done", "run.failed", "run.cancelled"]);
const RECONNECTING_MS = 1500;

/**
 * Plays each run's fixture events after `since`: at once (closing when the run has ended), one
 * by one on a timer (`timer`), or up to `dropAt`, then fails once more before replaying (`drop`).
 * An unknown run closes 4404; with `refuse` no socket ever opens.
 */
function previewSocket(
  events: Record<string, RunEvent[]>,
  known: (runId: string) => boolean,
  scenario: Scenario,
): SocketFactory {
  const connections = new Map<string, number>();
  return class {
    onopen: (() => void) | null = null;
    onmessage: ((message: { data: string }) => void) | null = null;
    onclose: ((close: { code: number }) => void) | null = null;
    private timers: ReturnType<typeof setTimeout>[] = [];
    constructor(url: string) {
      const parsed = new URL(url);
      const runId = decodeURIComponent(parsed.pathname.split("/")[3] ?? "");
      const since = Number(parsed.searchParams.get("since") ?? 0);
      const all = (events[runId] ?? []).filter((e) => e.seq > since || since === 0);
      const attempt = (connections.get(runId) ?? 0) + 1;
      connections.set(runId, attempt);
      if (!known(runId)) {
        this.later(50, () => this.onclose?.({ code: 4404 }));
        return;
      }
      if (scenario.refuse) {
        this.later(50, () => this.onclose?.({ code: 1006 }));
        return;
      }
      const drop = scenario.stream === "drop" && runId === scenario.runId;
      if (drop && attempt === 2) {
        this.later(50, () => this.onclose?.({ code: 1006 }));
        return;
      }
      const shown =
        drop && attempt === 1 ? all.filter((e) => e.seq <= (scenario.dropAt ?? 0)) : all;
      this.later(50, () => {
        this.onopen?.();
        if (scenario.stream === "timer" && runId === scenario.runId && attempt === 1) {
          return this.play(shown, 0);
        }
        for (const event of shown) this.emit(event);
        if (drop && attempt === 1)
          this.later(RECONNECTING_MS, () => this.onclose?.({ code: 1006 }));
        else if (shown.some((e) => TERMINAL.has(e.type))) this.onclose?.({ code: 1000 });
      });
    }
    private later(ms: number, run: () => void) {
      this.timers.push(setTimeout(run, ms));
    }
    /** Streamed scenarios happen now, so the elapsed time counts from the page load. */
    private emit(event: RunEvent) {
      const now = scenario.stream ? { ...event, ts: new Date().toISOString() } : event;
      this.onmessage?.({ data: JSON.stringify(now) });
    }
    private play(list: RunEvent[], i: number) {
      const event = list[i];
      if (!event) return;
      this.emit(event);
      if (TERMINAL.has(event.type)) return this.onclose?.({ code: 1000 });
      this.later(event.type === "report.delta" ? 40 : 160, () => this.play(list, i + 1));
    }
    close() {
      for (const timer of this.timers) clearTimeout(timer);
    }
  };
}

export function Preview({ name }: { name: string }) {
  const scenario = SCENARIOS[name];
  const [setup] = useState(() => {
    if (!scenario) return null;
    const route =
      scenario.screen === "report"
        ? { screen: "report" as const, runId: scenario.runId }
        : scenario.screen === "live" && scenario.runId
          ? { screen: "live" as const, runId: scenario.runId }
          : { screen: scenario.screen };
    window.history.replaceState(null, "", routeHash(route));
    const api = fakeApi(scenario.data);
    const shown = scenario.source;
    if (shown === "loading") api.source = () => new Promise(() => {});
    else if (shown) api.source = async () => sourceViews()[shown];
    return {
      makeApi: () => api,
      Socket: previewSocket(
        api.data.events,
        (runId) => api.data.runs.some((r) => r.run_id === runId),
        scenario,
      ),
      login: scenario.login?.(),
    };
  });
  useOpenSource(scenario);
  if (!setup) {
    return (
      <p>
        Unknown preview “{name}”. Scenarios: {Object.keys(SCENARIOS).join(", ")}.
      </p>
    );
  }
  return <App makeApi={setup.makeApi} Socket={setup.Socket} login={setup.login} />;
}

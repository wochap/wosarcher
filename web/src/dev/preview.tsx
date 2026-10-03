// Development only: #/preview/<name> renders the app on fake data, for the side-by-side
// comparison with the prototype's scenarios. main.tsx imports this module only when
// import.meta.env.DEV, so production builds leave it out.
import { useState } from "react";
import type { SocketFactory } from "../api/events";
import type { RunEvent } from "../api/types";
import { App } from "../app/App";
import { routeHash, type Screen } from "../app/route";
import type { LoginState } from "../screens/login/LoginScreen";
import { type FakeData, fakeApi } from "../test/fakeApi";

type Scenario = { screen: Screen; data?: Partial<FakeData>; login?: () => LoginState };

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
};

/** Replays a run's fixture events, then stays open like a live run. */
function previewSocket(events: Record<string, RunEvent[]>): SocketFactory {
  return class {
    onopen: (() => void) | null = null;
    onmessage: ((message: { data: string }) => void) | null = null;
    onclose: ((close: { code: number }) => void) | null = null;
    constructor(url: string) {
      const runId = decodeURIComponent(new URL(url).pathname.split("/")[3] ?? "");
      setTimeout(() => {
        this.onopen?.();
        for (const event of events[runId] ?? []) this.onmessage?.({ data: JSON.stringify(event) });
      }, 50);
    }
    close() {}
  };
}

export function Preview({ name }: { name: string }) {
  const scenario = SCENARIOS[name];
  const [setup] = useState(() => {
    if (!scenario) return null;
    window.history.replaceState(null, "", routeHash({ screen: scenario.screen }));
    const api = fakeApi(scenario.data);
    return {
      makeApi: () => api,
      Socket: previewSocket(api.data.events),
      login: scenario.login?.(),
    };
  });
  if (!setup) {
    return (
      <p>
        Unknown preview “{name}”. Scenarios: {Object.keys(SCENARIOS).join(", ")}.
      </p>
    );
  }
  return <App makeApi={setup.makeApi} Socket={setup.Socket} login={setup.login} />;
}

// Opens a run scenario fixture in the whole app and plays its events into the fake sockets.
import { act, waitFor } from "@testing-library/react";
import type { RunEvent } from "../api/types";
import { FakeWebSocket } from "./FakeWebSocket";
import { type FakeApi, fakeApi } from "./fakeApi";
import type { Fixture } from "./fixtures/sample";
import { renderApp } from "./renderApp";

export const socketsFor = (runId: string) =>
  FakeWebSocket.instances.filter((s) => s.url.includes(`/runs/${runId}/`));

/** Opens every socket of `runId` and sends `events`. */
export async function play(runId: string, events: RunEvent[]) {
  await waitFor(() => expect(socketsFor(runId).length).toBeGreaterThan(0));
  await act(async () => {
    for (const socket of socketsFor(runId)) {
      if (socket.readyState === 0) socket.open();
      socket.emit(...events);
    }
  });
}

export function scenarioHash(fixture: Fixture): string {
  if (fixture.screen === "report") return `#/runs/${fixture.runId}`;
  if (fixture.screen === "live" && fixture.runId) return `#/live/${fixture.runId}`;
  return `#/${fixture.screen}`;
}

/** Renders the app at the fixture's screen; plays `events` (default: all) of its run. */
export async function openScenario(
  fixture: Fixture,
  { api = fakeApi(fixture.data), events }: { api?: FakeApi; events?: RunEvent[] } = {},
) {
  const result = renderApp({ hash: scenarioHash(fixture), api });
  const runId = fixture.runId;
  if (runId) await play(runId, events ?? api.data.events[runId] ?? []);
  return { ...result, api };
}

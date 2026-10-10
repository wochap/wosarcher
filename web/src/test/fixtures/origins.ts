// Scenarios `queued` and `queued-cli` (a run waiting for a run slot) and `live-cli` and
// `live-api` (a running run started from the CLI or with an API token).
import type { Origin, RunEvent } from "../../api/types";
import { ev } from "../events";
import { live } from "./live";
import { type Fixture, otherRuns, RUN_ID, summary } from "./sample";

/** Two slots, held by runs that started a little before now. */
function queuedBehind(origins: Origin[]): RunEvent[] {
  const held = origins.map((origin, n) => ({
    run_id: ["r_8c0d", "r_8b90"][n] ?? `r_8b9${n}`,
    origin,
    token_name: null,
    started: new Date(Date.now() - (n ? 246_000 : 72_000)).toISOString(),
  }));
  return [ev(0, "run.queued", { position: 1, limit: 2, held }, null, RUN_ID)];
}

function queuedFixture(origins: Origin[]): Fixture {
  return {
    screen: "live",
    runId: RUN_ID,
    data: {
      runs: [summary({ status: "queued", duration_s: null, cost: null }), ...otherRuns],
      events: { [RUN_ID]: queuedBehind(origins) },
    },
  };
}

export const queued = queuedFixture(["web", "cli"]);
export const queuedCli = queuedFixture(["cli", "cli"]);

/** The live scenario stopped while it runs, started from `origin`. */
function runningFrom(origin: Origin, token_name: string | null = null): Fixture {
  const events = (live.data.events?.[RUN_ID] ?? []).slice(0, 20);
  return {
    ...live,
    stream: undefined,
    data: {
      ...live.data,
      runs: [
        summary({ status: "running", duration_s: null, cost: null, origin, token_name }),
        ...otherRuns,
      ],
      events: { [RUN_ID]: events },
    },
  };
}

export const liveCli = runningFrom("cli");
export const liveApi = runningFrom("api", "ci-runner");

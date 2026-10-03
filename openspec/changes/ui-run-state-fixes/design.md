# Design: ui-run-state-fixes

## Context

See proposal.md for why. This change runs after `server-robustness`, and
relies on these contracts from it (its specs `run-queue` "Cancel",
`http-api` run summary, `event-streaming` "Live-only event sequence
numbers" and "Stream end"):

- `POST /api/runs/{id}/cancel` for a known run that is not queued or
  running answers 409 `{"error": "run_not_active", "detail", "run_id",
  "status"}`; an unknown run 404 `run_not_found`.
- `RunSummary` (and `RunDetail`) gain `error` (the `run.failed` error text,
  null unless failed) and `end_stage` (the stage named by `run.failed` or
  `run.cancelled`, else null). `web/src/api/generated.ts` is regenerated
  by that change.
- A run that ended without a run directory answers `GET /api/runs/{id}`
  200 with its status and `last_seq = 0`, and its socket sends one terminal
  event with `seq 0` and closes 1000. Terminal events that are not logged
  carry a `seq` no greater than the client's last `seq`; clients apply
  terminal events whatever their `seq`.
- The socket decides queued/running/ended after accepting, so it no longer
  hangs.

Current client (read before writing this design):

- `RunEvents` (`web/src/api/events.ts`) reconnects every `RECONNECT_MS`
  (2000) forever; `reconnect()` reports `replaying` before `open()`, so a
  socket that never opens alternates "Reconnecting" and "Replaying"; a
  `getRun` error (404 included) retries forever; `conn.notFound` is set
  on 4404 but nothing reads it.
- `runReducer` drops every non-live-only event with `seq <= lastSeq`,
  including terminal events with `seq 0`.
- `useRun` calls `getRun` once, only to detect `interrupted`; `reduce`
  keeps `interrupted` against later events.
- `LiveHeader` shows Cancel for `queued`/`running` from the view;
  `LiveScreen.attempt` toasts any error.
- `useRunData.useAncestors` keeps one `RunEvents` on `chain.at(-1)` and
  closes it when the chain grows (Fable §4.3); `RunStore.fork` writes
  `copied_from = parent_id` and `version = parent.version + 1`.
- `ReportScreen` returns `null` while `detail` is null; `useRunData`
  swallows the `getRun` rejection.
- `ProvidersSection` `ROLES` maps `embeddings`/`scorer`; the server sends
  `prefilter`/`score` (`ProviderCheck.role = row.block`); the fixture
  `web/src/test/fixtures/data.ts` uses the wrong names.
- `App` follows `newestActive(listRuns())` only in the `getSession`
  success branch; `unlock` bumps `epoch`, which that effect ignores.

## Goals / Non-Goals

**Goals:** the Live run screen is never stuck on a state the server has
left; the reconnect sequence is finite and honest; fork lineage data
appears for any depth.

**Non-Goals:** see proposal.md. No polling while the socket is connected;
no change to the event socket protocol.

## Decisions

1. **Summary as a reducer input.** `RunEvents` emits a third update kind,
   `{kind: "summary", detail: RunDetail}`, from every `getRun` it makes:
   one at `start()` (in parallel with the first socket) and one before each
   reconnect attempt. `useRun` dispatches it as `{summary}`; its separate
   `getRun` for `interrupted` goes away. `applySummary(view, detail)` in
   `reducer.ts`: when `detail.status` is ended (`done`, `failed`,
   `cancelled`, `interrupted`) and `view.status` is `queued` or `running`,
   set `status`; for `failed` also `failure = {stage: end_stage ?? "",
   error: error ?? ""}` and that phase `failed`, other open phases
   `cancelled` (as `run.failed` does); for `cancelled` the open phases
   `cancelled`. The existing guard in `useRun.reduce` generalises from
   `interrupted` to any ended status: an ended status is never replaced by
   `queued`/`running`. Alternative: poll `GET /api/runs/{id}` on a timer
   whenever the socket is not connected — more requests for no benefit,
   since reconnect attempts already read it.

2. **Terminal events bypass `seq` dedupe.** In `runReducer`, `run.done`,
   `run.failed`, `run.cancelled` are applied even when `seq <= lastSeq`,
   and `lastSeq` becomes `max(lastSeq, seq)`. Re-applying a terminal event
   is idempotent (same status, same `endedAt`). One `TERMINAL` set is
   exported from `api/events.ts` and used by the reducer (removing the
   reducer's duplicate `LIVE_ONLY` is in scope, as the same file is
   touched; Fable §4.7 duplicate).

3. **Reconnect state machine in `RunEvents`.**
   - `delay(attempt) = min(2000 * 2^(attempt-1), 30000)`; `attempt`
     resets to 0 when a socket opens.
   - `failedOpens` counts consecutive sockets that closed before `onopen`;
     reset on open. At 3, `conn.state = "unavailable"` (new `ConnState`).
   - `reconnect()` stores the pending replay count (`last_seq - since`) but
     reports `replaying` from `onopen` only.
   - `getRun` rejected with `ApiError` 404 → `closed` with
     `notFound: true`, stop. Other errors → schedule the next attempt (a
     401 has locked the app; the next attempt after sign-in succeeds).
   - Summary says ended and (`last_seq <= this.lastSeq` or state is
     `unavailable`) → `closed`, stop; the summary update has already set
     the status.
   - While `unavailable`, the 30 s attempts continue for running runs;
     each attempt's summary keeps the header current.
   Alternative: stop after N failures and offer a "Retry" button; the
   prototype has no button in banners, and automatic slow retries recover
   on their own when a proxy is fixed.

4. **Cancel result.** `ApiClient.cancelRun` returns `Promise<CancelOutcome>`
   = `{kind: "signalled" | "dequeued"} | {kind: "not_active", status:
   RunStatus}`; `httpApi` maps a 409 whose body has `error ===
   "run_not_active"` (the generated `RunNotActive` type from
   `server-robustness`) to the latter instead of throwing. `useRun` exposes
   `refresh()` (one `getRun` → summary dispatch; a 404 sets not found).
   `LiveScreen` on `not_active` dispatches the body's status as a summary
   with only `status` (the follow-up `refresh()` fills `error`/`end_stage`)
   and shows no toast. `LiveHeader` takes `cancelling: boolean` and
   disables the button while true. Alternative: keep throwing and catch
   `ApiError` by code in the screen — leaks HTTP detail into a screen.

5. **New UI states reuse prototype styles.** `StatusBanner` gets an
   `unavailable` branch with tone `warn` and `WifiSlash`, highest priority
   after `reconnecting`. `LiveFooter` `CONN` gains `unavailable: "Live
   updates unavailable"`, dot `data-state="unavailable"` styled as the
   warn dot without pulse. `NotFound` (`screens/live/NotFound.tsx`) reuses
   `EmptyLive.module.css` with `Question` icon; `LiveScreen` renders it when
   `live.conn.notFound` (or `data.notFound`), `ReportScreen` when
   `useRunData(...).notFound`. `useRunData` sets `notFound` when its
   `getRun` rejects with `ApiError` status 404. These are recorded in
   docs/design.md "Frontend decisions" as additions to the prototype.

6. **One `copied_from` hop always reaches the executing run.**
   `RunStore.fork` writes `copied_from = done[stage].data.copied_from or
   parent_id`. Then the UI needs no chain walking: the runs to follow are
   the distinct `copiedFrom` values of the view's reused phases.
   `useAncestors` becomes `useSources(view)`: a `Map<runId, RunEvents>` in a
   ref; an effect keyed on the sorted, joined id list opens a stream for
   each new id and never closes one until the hook unmounts or the id
   leaves the list (a stream ends by itself at its run's terminal event).
   `ranIn(phase)` = the view of `phase.copiedFrom` when the phase is
   reused, else the run itself. Alternative (keep immediate-parent
   `copied_from`, follow multiple hops in the UI): needs streams for runs
   that never ran the stage, and the bug class Fable found.

7. **Version = lineage max + 1, computed by the store.** `RunStore.fork`
   finds the lineage root by following `parent_run_id` through
   `read_record` (stopping at a missing or repeated id), then scans the
   runs directory's records (`request.json` only) for runs whose chain
   reaches that root, and uses the highest `version` plus one. Forks are
   rare and the scan reads small files, so no index. The UI already
   computes `max(lineage) + 1` (`ReportScreen` `nextVersion`), which now
   matches; only its test is added.

8. **Provider role names.** `ROLES` keys become the server's block names
   (`prefilter: "Embeddings"`, `score: "Scorer"`); an unknown block is
   capitalised. The fixture uses `prefilter`/`score`, so the test fails on
   the old mapping.

9. **Follow after sign-in.** Extract `followActive()` in `App` (calls
   `listRuns` and `follow(f => f ?? newestActive(runs))`); call it after
   a successful session check and in `unlock`.

## Risks / Trade-offs

- [A slow reverse proxy makes the first three handshakes fail, then
  works] → the 30 s retry recovers and the banner switches back to the
  reconnect sequence; status stays right meanwhile.
- [Summary and replayed events race (summary says failed, then a replayed
  `run.failed` arrives)] → terminal events are idempotent; the ended-status
  guard keeps non-terminal events from reopening.
- [Existing runs on disk have immediate-parent `copied_from`] → alpha, no
  shim; such multi-hop forks show the intermediate run's panels empty as
  before. Recorded in proposal Non-goals.
- [Version scan cost with many runs] → only on fork; reads `request.json`
  per run; acceptable for a single-user tool.

## Migration Plan

Deploy after `server-robustness` (needs the 409 body and summary fields;
without them a 409 still maps to `not_active` only if the body has
`error = "run_not_active"`, which the current server already sends, with
`status` missing → treated as unknown and resolved by `refresh()`).

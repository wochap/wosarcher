# Proposal: ui-run-state-fixes

## Why

In the first live deployment a run failed, but the UI kept showing it as
running even after a reload: the event WebSocket never connected, and the UI
takes run status only from events. Cancel then showed the server's
"run <id> is not queued or running" error. The reconnect banner looped
between "Connection lost" and "Reconnected. Replaying N missed events…"
because the client announces a replay before the socket has opened and
retries every 2 s forever. The Fable review found more stuck states in the
same area: terminal events with `seq 0` (cancelling a queued run, a crash
before the run directory exists) are dropped as duplicates (§4.1); an
unknown run is never shown as not found (§4.2); multi-hop fork lineage
shows empty panels (§1.3, §4.3); the Rewrite dialog's version number
disagrees with the server (§4.6); provider cards show raw keys (§4.4); and
Live run does not follow the active run after signing in at start (§4.5).

## What Changes

- **Status from the server, not only from events.** On load, after every
  reconnect attempt, and when Cancel answers 409, the UI reads
  `GET /api/runs/{id}` and applies its `status`, `error`, and `end_stage`
  (fields added by change `server-robustness`) when the run has ended.
  Events cannot reopen an ended run.
- **Terminal events whatever their `seq`.** `run.done`, `run.failed`, and
  `run.cancelled` are applied even when their `seq` is not above the last
  applied one, without moving it (the rule `server-robustness` states for
  the socket).
- **Cancel.** Shown only while the run is queued or running, disabled while
  the request is in flight. A 409 `run_not_active` answer is not an error:
  the UI applies the `status` from the body, refreshes the run, and the
  button disappears.
- **Reconnect with back-off and a clear end state.** "Replaying" is shown
  only after the new socket has opened. Retries wait 2, 4, 8, 16, then
  30 seconds. After three attempts in a row whose socket never opened, the
  Live run screen shows "Live updates unavailable" (a banner styled as the
  `reconnecting` scenario) and the footer says so; retries continue every
  30 s and each refreshes the run status, so an ended run shows as ended.
  A 404 from `GET /api/runs/{id}` stops retrying and shows "Run not found".
- **Run not found** on the Live run and Report screens (socket 4404 or
  `GET /api/runs/{id}` 404), laid out as the `empty` scenario.
- **Fork lineage** (server and UI): a copied `stage.done` keeps the
  `copied_from` of the parent's event when it has one, so it always names
  the run that executed the stage; a fork's version is the highest version
  in its lineage plus one (unique, and what the Rewrite dialog announces);
  the UI follows every run named by `copied_from` with its own stream,
  kept open until that stream ends.
- **Provider cards** map the server's block names (`search`, `fetch`,
  `prefilter`, `score`, `llm`) to Search, Fetch, Embeddings, Scorer, LLM.
- **Follow the active run after sign-in.** The newest queued or running
  run is followed after the sign-in screen closes, not only when the
  session check succeeds at start.
- docs/design.md "Frontend decisions", "Frontend structure", "Commands"
  (fork lineage), and "Server" (lineage) updated.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-shell`: "Run event stream" (terminal events, status from the
  server, back-off, unavailable state, 404), "Settings providers" (role
  names), "Sign in" (follow the active run after sign-in).
- `web-run`: "Live run header" (Cancel), "Reconnecting state"
  (replaying only after open), new "Live updates unavailable state" and
  "Run not found state", "Rewrite" (version number).
- `run-store`: "Fork" (`copied_from` names the run that ran the stage),
  "Lineage" (version is the lineage's highest plus one).
- `cli-run`: "Fork command" scenario wording for the version.

## Non-goals

- A new design export (help tooltips or other new prototype states). The
  two new states reuse the `reconnecting` and `empty` scenarios' styles.
- Server changes owned by `server-robustness` (cancel 409 body, summary
  `error`/`end_stage`, remembered runs without a directory, socket
  handshake fix); this change consumes them.
- Fable §4.7 small items other than the reconnect-forever-on-404 bullet
  (login error handling, `R` shortcut on the lock screen, duplicated
  helpers, redundant requests), §3.5 (order of copied events).
- Migrating existing run directories whose copied events name the
  immediate parent (alpha: no compatibility shim; re-fork if needed).

## Impact

- Frontend: `web/src/api/events.ts`, `web/src/api/client.ts`
  (`cancelRun` result), `web/src/run/reducer.ts`, `web/src/run/useRun.ts`,
  `web/src/run/useRunData.ts`, `web/src/app/App.tsx`,
  `web/src/screens/live/{LiveScreen,LiveHeader,StatusBanner,LiveFooter}.tsx`,
  new `web/src/screens/live/NotFound.tsx`,
  `web/src/screens/report/ReportScreen.tsx`,
  `web/src/screens/settings/ProvidersSection.tsx`,
  `web/src/test/fixtures/data.ts`, `web/src/test/fakeApi.ts`, and their
  tests.
- Backend: `src/wosarcher/store/__init__.py` (`RunStore.fork`), tests in
  `tests/test_store.py`.
- Depends on change `server-robustness` (409 body with `status`;
  `RunSummary.error`, `RunSummary.end_stage`; regenerated
  `web/src/api/generated.ts`).
- docs/design.md sections "Commands", "Server", "Frontend decisions",
  "Frontend structure".

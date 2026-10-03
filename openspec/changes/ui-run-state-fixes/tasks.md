# Tasks

Prerequisite: change `server-robustness` is applied (409 `run_not_active`
body with `status`; `RunSummary.error`/`end_stage`; regenerated
`web/src/api/generated.ts`).

## 1. Fork lineage in the store

- [ ] 1.1 In `src/wosarcher/store/__init__.py` `RunStore.fork`, write `copied_from = done[stage].data.copied_from or parent_id` for each copied `stage.done` (design decision 6). Test `tests/test_store.py::test_fork_of_fork_copied_from`: A full run (fake), B = fork(A, `score`), C = fork(B, `write`); assert C's copied events for `plan`..`prefilter` have `copied_from == A` and for `score`, `select` have `copied_from == B`. Verify: `uv run pytest tests/test_store.py` passes.
- [ ] 1.2 In `RunStore.fork`, set `version` to the highest `version` among the runs of the parent's lineage plus one (design decision 7; a helper `lineage_versions(parent_id) -> list[int]` in the store). Tests in `tests/test_store.py`: `test_second_fork_version` (A→B→C gives 1, 2, 3) and `test_two_forks_of_first_version` (A→B, then A→D gives D version 3). Verify: both pass.
- [ ] 1.3 Update docs/design.md "Commands" (`fork`: version is the lineage's highest plus one; copied `stage.done` names the run that executed the stage) and "Server" (lineage paragraph). Verify: neither section says "parent version plus one".

## 2. Run status and terminal events in the client

- [ ] 2.1 In `web/src/run/reducer.ts`, apply `run.done`, `run.failed`, `run.cancelled` whatever their `seq` and set `lastSeq = max(lastSeq, seq)`; import `LIVE_ONLY` and a new exported `TERMINAL` from `web/src/api/events.ts` instead of the local copy. Test in `web/src/run/reducer.test.ts`: `run.cancelled` with `seq: 0` on a fresh view gives status `cancelled` and `lastSeq` 0; a duplicate `run.done` leaves the view equal. Verify: `pnpm --dir web test reducer` passes.
- [ ] 2.2 Add `applySummary(view, detail)` to `reducer.ts` (design decision 1). Tests: summary `failed` with `end_stage: "fetch"`, `error: "no output"` on a running view → status failed, Fetch phase failed with the error, failure set; summary `cancelled` → open phases cancelled; summary `running` → view unchanged; summary on an already ended view → unchanged. Verify: `pnpm --dir web test reducer` passes.
- [ ] 2.3 In `web/src/run/useRun.ts`, handle `{kind: "summary"}` updates by dispatching `{summary}`, remove the separate `getRun` for `interrupted`, generalise the guard so an ended status is never replaced by `queued`/`running`, and expose `refresh()` (one `getRun` → summary; 404 → `notFound`). Tests in `web/src/run/useRun.test.tsx`: "summary failed, socket never opens" (the scenario `Failed run, socket never opens`); "replayed run.started after a failed summary keeps failed". Verify: `pnpm --dir web test useRun` passes.

## 3. Reconnect state machine

- [ ] 3.1 In `web/src/api/events.ts`: add `ConnState` `"unavailable"`; emit `{kind: "summary", detail}` from the `getRun` at `start()` (new, in parallel with the first socket) and before each attempt; back-off `min(2000 * 2^(attempt-1), 30000)` with `attempt` reset on open; report `replaying` from `onopen` only (design decision 3). Tests in `web/src/api/events.test.ts` with fake timers and `FakeWebSocket.serverClose(1006)` without `open()`: waits are 2 s, 4 s, 8 s; state is never `replaying` while no socket opened; after a successful open following a drop, `replaying` with the right count, then `connected`. Verify: `pnpm --dir web test events` passes.
- [ ] 3.2 In `events.ts`: count consecutive sockets closed before open; at 3 report `unavailable` and keep 30 s attempts; a `getRun` rejected with `ApiError` 404 reports `closed` with `notFound: true` and stops; a summary with an ended status stops retrying when `last_seq <= lastSeq` or the state is `unavailable`. Tests: "handshake keeps failing" (scenario in the web-shell delta), "404 before an attempt stops", "ended while unavailable stops", "open after unavailable returns to replaying". Verify: `pnpm --dir web test events` passes.
- [ ] 3.3 Update docs/design.md "Frontend structure" (`RunEvents` paragraph: back-off, `unavailable`, summary updates, 404) and "Frontend decisions" (new bullet: "Live updates unavailable" banner and footer state, and "Run not found", both using prototype styles from `reconnecting` and `empty`). Verify: the paragraph no longer says "reconnects 2 s after any close".

## 4. Live run screen (design scenarios `reconnecting`, `failure`, `empty`)

- [ ] 4.1 `web/src/api/client.ts`: `cancelRun` returns `CancelOutcome` (design decision 4); a 409 with `error: "run_not_active"` resolves to `{kind: "not_active", status}`. Update `web/src/test/fakeApi.ts` to answer the same way for an ended run. Test in `web/src/api/client.test.ts`: 409 body `{"error":"run_not_active","detail":"…","run_id":"r1","status":"failed"}` resolves to `{kind: "not_active", status: "failed"}`; 500 still throws `ApiError`. Verify: `pnpm --dir web test client` passes.
- [ ] 4.2 `LiveScreen.tsx`/`LiveHeader.tsx`: Cancel disabled while the request is in flight (`cancelling` prop); on `not_active` dispatch the status and call `live.refresh()`, no toast. Tests in `LiveScreen.test.tsx`: "cancel a run that already failed" (web-run delta scenario: no toast, tag Failed, Rerun shown, Cancel gone), "cancel in flight disables the button". Verify: tests pass; compare the result with prototype scenario `failure` in `pnpm --dir web dev` (`#/preview/failure`).
- [ ] 4.3 `StatusBanner.tsx`: `unavailable` branch (warn, `WifiSlash`, text from the web-run delta). `LiveFooter.tsx`: `CONN.unavailable = "Live updates unavailable"` and a static warn dot in `LiveFooter.module.css` for `data-state="unavailable"`. Tests in `LiveFooter.test.tsx` and `LiveScreen.test.tsx` ("upgrade refused" scenario: banner never alternates with "Replaying"). Add preview `unavailable` in `web/src/dev/preview.tsx` (socket never opens). Verify: tests pass; `#/preview/unavailable` matches the banner and footer style of prototype scenario `reconnecting`.
- [ ] 4.4 New `web/src/screens/live/NotFound.tsx` (layout and CSS of `EmptyLive`, `Question` icon, "Run not found", "Run <id> does not exist on this server. It may have been deleted.", New run button with Alt 1). `LiveScreen` renders it on `live.conn.notFound`. Test in `LiveScreen.test.tsx`: socket closes 4404 → "Run not found", no footer. Add preview `notFound`. Verify: test passes; `#/preview/notFound` matches prototype scenario `empty` apart from icon and texts.

## 5. Report screen and lineage (design scenarios `finished`, `versions`)

- [ ] 5.1 `web/src/run/useRunData.ts`: add `notFound` (its `getRun` rejected with `ApiError` 404); `ReportScreen.tsx` renders `NotFound` when set. Test in `ReportScreen.test.tsx`: `#/runs/<deleted id>` shows "Run not found" with the id. Verify: test passes.
- [ ] 5.2 Replace `useAncestors` with `useSources` (design decision 6): one `RunEvents` per distinct `copiedFrom` of reused phases, kept until unmount or until the id leaves the set; `withAncestors` takes `Record<runId, RunView>` and uses `copiedFrom` per phase. Test in `useRunData.test.tsx`: two-hop lineage (C copies plan..prefilter from A and score, select from B) with A's and B's events emitted in separate `act` calls after C's; assert C's sources come from A and passages from B, and neither A's nor B's socket was closed by the client before its `run.done`. Verify: `pnpm --dir web test useRunData` passes; `#/preview/versions` still matches prototype scenario `versions`.
- [ ] 5.3 `ReportScreen.test.tsx`: viewing v1 of a lineage with v1 and v2, the Rewrite dialog says "Creates v3". Verify: test passes (no code change expected).

## 6. Settings and sign-in

- [ ] 6.1 `ProvidersSection.tsx`: `ROLES` keyed by server block names (`search`, `fetch`, `prefilter` → "Embeddings", `score` → "Scorer", `llm`), unknown blocks capitalised. Fix `web/src/test/fixtures/data.ts` roles to `prefilter`/`score`. Test in `ProvidersSection.test.tsx`: cards titled Search, Fetch, Embeddings, Scorer, LLM; no card titled `prefilter`. Verify: test passes; Settings matches the prototype's provider cards.
- [ ] 6.2 `App.tsx`: extract `followActive()` and call it after a successful session check and in `unlock` (design decision 9). Test in `App.test.tsx`: start with `getSession` 401 and a running run in `listRuns`; sign in; Alt+2 shows that run and the Live run item has the dot. Verify: `pnpm --dir web test App` passes.

## 7. Gate

- [ ] 7.1 Verify `scripts/check --full` passes and `openspec validate ui-run-state-fixes --strict` passes.

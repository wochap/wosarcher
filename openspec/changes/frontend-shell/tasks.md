# Tasks

Visual checks in this file are manual: open `design/project/Sift
Research.dc.html` with the named scenario next to the built page (or
`#/preview/<name>` in `pnpm --dir web dev`), in the dark and light themes,
at 1440px and 390px wide, and compare layout, sizes, colors, icons, and
text.

## 1. Project scaffold

- [ ] 1.1 Create `web/package.json` (pnpm, `"type": "module"`, scripts `dev`, `build` = `tsc --noEmit && vite build`, `test` = `vitest run`, `gen:types`, `check:types`), dependencies react, react-dom, react-markdown, @phosphor-icons/react, @fontsource/inter, dev dependencies vite, @vitejs/plugin-react, typescript, @biomejs/biome, vitest, jsdom, @testing-library/react, @testing-library/user-event, json-schema-to-typescript; verify `pnpm --dir web install` succeeds and `scripts/check-frontend` is no longer skipped
- [ ] 1.2 Add `web/tsconfig.json` (strict, `jsx: react-jsx`, `moduleResolution: bundler`, includes `src` and `vite.config.ts`), `web/vite.config.ts` (React plugin, Vitest `environment: jsdom`, dev proxy for `/api` (HTTP and WebSocket) to `WOSARCHER_DEV_API` (default `http://127.0.0.1:8765`) with the `Origin` header rewritten), `web/index.html`, and `web/src/main.tsx` rendering an empty `App`; verify `pnpm --dir web build` writes `web/dist/index.html` and a smoke test `src/app/App.test.tsx` renders `App`
- [ ] 1.3 Add `web/biome.json` (Biome 2, includes `["**", "!dist", "!src/vendor", "!src/api/generated.ts"]`, 2-space indent, width 100, recommended rules) and add `web/node_modules` and `web/dist` to `.gitignore`; verify `scripts/check-frontend` passes

## 2. Styles, fonts, icons

- [ ] 2.1 Copy `design/project/_ds/nocturne-*/styles.css` to `web/src/vendor/nocturne.css`, removing only the Google Fonts `@import` line (replace it with a comment naming @fontsource/inter); verify `diff` against the source shows only that line
- [ ] 2.2 Create `web/src/vendor/prototype.css` from the prototype's `<style>` block (lines 17 to 26) with `.sx` rescoped to `:root` and `.sx[data-theme=light]` to `:root[data-theme="light"]`, and `web/src/app.css` with the root sizing (`html, body, #root` full height), base `font-size: 13.5px; line-height: 1.5; font-variant-numeric: tabular-nums`, and the shared `.spin` and `.pulse` classes; import both plus `nocturne.css` and Inter 400/500/600/700 in `main.tsx`; verify `scripts/check-frontend` passes (no token violations outside vendor) and a test asserts `main.tsx` imports no `http` URL
- [ ] 2.3 Verify after `pnpm --dir web build` that `web/dist/assets` contains the Inter woff2 files and that `grep -rE "https?://(fonts\.|unpkg|cdn)" web/dist` finds nothing; then open the built page and confirm (manual) that the network panel shows only same-origin requests (spec: Self-contained assets)

## 3. Generated types

- [ ] 3.1 Write `web/scripts/gen-types.mjs` (runs `uv run --frozen wosarcher schema` from the repository root, compiles with json-schema-to-typescript `unreachableDefinitions: true`, writes `src/api/generated.ts`; `--check` compares and exits 1 with the regenerate hint) and commit the generated file; verify `pnpm --dir web run check:types` passes, and fails after adding a field to a local copy of the schema (test `scripts/gen-types.test.mjs` run by Vitest with a stubbed schema)
- [ ] 3.2 Add `pnpm --dir web run check:types` to the `--full` section of `scripts/check`; verify `scripts/check --full` runs it (spec: Generated types)

## 4. Data layer

- [ ] 4.1 Implement `src/api/client.ts`: the `ApiClient` interface, `ApiError`, and `httpApi(onUnauthorized)` for every endpoint in design.md (including `rerunRun(id)` → `POST /api/runs/{id}/rerun`), `login` returning `ok | wrong | limited`; verify `client.test.ts` with a stubbed `fetch`: JSON error to `ApiError` with field errors, 401 calls `onUnauthorized`, login 401 and 429 map to `wrong` (attempts left) and `limited` (`retry_after`), `createRun` sends multipart, `rerunRun` posts with no body
- [ ] 4.2 Implement `src/test/fakeApi.ts` (in-memory `ApiClient` from fixture data, records calls) and `src/test/FakeWebSocket.ts`; verify their own small tests
- [ ] 4.3 Implement `src/run/reducer.ts` (`RunView`, `initialRunView`, `runReducer`) for every event type in docs/design.md "Events" plus `report.snapshot`; verify `reducer.test.ts`: dedupe by `seq`, live-only `run.queued`/`report.delta`/`report.snapshot` applied without moving `lastSeq`, delta append and snapshot replace, `copied_from` to reused, `skipped` flag, device from `stage.started`, wait reason from `resource.waiting`, waiting then running then done, failure keeps stage and error, cancel marks the running phase cancelled, `stage.done` token and cost sums, sources found/fetched/failed with reason, kept counts from `passages.scored` (spec: Run view state, Run event stream)
- [ ] 4.4 Implement `src/api/events.ts` (`RunEvents`): connect to `/api/runs/{id}/events?since=0`, on a close other than 1000/4404 wait 2 s, call `api.getRun` (401 locks), reconnect with `since` = last applied logged `seq` and an attempt count, `replaying` until `seq >= last_seq` with `replayed = last_seq - since`, no reconnect after a terminal event or 1000, `notFound` on 4404; verify `events.test.ts` with `FakeWebSocket`, `fakeApi`, and fake timers: drop at seq 351 reconnects with `since=351`, attempts count 1, 2, 3, replayed count from `last_seq`, 4408 reconnects, 1000 and 4404 do not (spec: Run event stream)
- [ ] 4.5 Implement `src/run/useRun.ts` (RunEvents plus reducer, exposes view and connection state, closes on unmount); verify `useRun.test.tsx` renders a probe component that shows the status after fixture events

## 5. App shell

- [ ] 5.1 Implement `src/app/route.ts` (hash parse, `go`, `useRoute`); verify `route.test.ts` for every route in design.md, unknown hash to `#/new`, and reload keeping the screen (spec: Screen URLs and API paths)
- [ ] 5.2 Implement `src/app/theme.ts` (initial theme from storage key `wosarcher-theme`, else `prefers-color-scheme`; sets `data-theme` on `<html>`; storage access in try/catch); verify `theme.test.ts` for first visit light, remembered choice, and blocked storage (spec: Theme)
- [ ] 5.3 Implement `src/app/Shell.tsx` and `Shell.module.css`: desktop sidebar (184px, brand "wosarcher", four items with icons and Alt hints, active tint and `aria-current`, Live active on Report, live and warn dots, theme toggle, socket origin of the page) and the phone top bar below 720px (`useIsPhone` with `matchMedia`); verify `Shell.test.tsx` for active item, Live active on Report, both dots, no "Sift" text, phone labels; compare with the prototype scenarios `new` and `live`, desktop and `device=phone` (manual) (spec: Design source and name, Desktop navigation, Phone navigation)
- [ ] 5.4 Implement `src/app/keys.ts` and the overlay stack in `UiContext` (Alt+1..4 by `e.code`, Escape closes the top overlay by priority alertdialog > dialog > tooltip, `/` focuses History search, nothing while locked); verify `keys.test.tsx` (spec: Keyboard shortcuts)
- [ ] 5.5 Implement `src/components/Toast.tsx` (+ module CSS) with `useToast()` (2.2 s, 6 s with Undo, replace) and `src/components/Dialog.tsx` (`.dialog-backdrop`/`.dialog`, `role` dialog or alertdialog, `aria-modal`, backdrop click closes form dialogs only); verify `Toast.test.tsx` and `Dialog.test.tsx` with fake timers (spec: Toasts)
- [ ] 5.6 Implement `src/components/Seg.tsx`, `Tag.tsx`, and `StatusTag.tsx` (completed, running spinning, failed, cancelled variants from the prototype's history tags via `data-state`); verify `StatusTag.test.tsx` renders each icon and label
- [ ] 5.7 Implement `src/app/App.tsx` with Auth, Ui, and Api contexts, the followed run (newest queued or running run at start), the screen switch, and placeholder `screens/new`, `screens/live`, `screens/report` components that show only their title; verify `App.test.tsx` with `fakeApi`: start picks the running run as followed, Alt+2 opens it

## 6. Sign in

- [ ] 6.1 Implement `src/screens/login/LoginScreen.tsx` (+ module CSS): overlay with radial glow, brand, "Sign in", text with "wosarcher instance", password field with show/hide, disabled submit when empty, page host below; App shows it on 401 or no session and keeps the screen behind; verify `LoginScreen.test.tsx` for success unlocking and session-expired returning to History; compare with the prototype scenario `login` (manual) (spec: Sign in)
- [ ] 6.2 Add the `wrong` state (danger alert with attempts left, `aria-invalid`, danger border, field emptied and refocused); verify a test with `fakeApi` answering 3 attempts left; compare with `login-wrong` (manual) (spec: Wrong password)
- [ ] 6.3 Add the `limited` state (warn alert with `m:ss`, 2px shrinking bar, disabled field, "Try again in N s" with lock icon, 1 s countdown, back to idle at zero); verify a test with fake timers for 30 then 29 and the end of the pause; compare with `login-limited` (manual) (spec: Sign-in paused)

## 7. Settings

- [ ] 7.1 Implement `src/screens/settings/ProvidersSection.tsx` (+ CSS): H1 with "Check all providers", profile line from `GET /api/profiles`, provider cards with kicker, name, `dl` of base URL and model, health strip for ok, degraded, down, skipped, and checking, one health request for a card's Check and for Check all with every card checking and every Check disabled meanwhile, profile line naming the checked profile and device labels, "N s ago"; feed the Settings nav dot; verify `ProvidersSection.test.tsx` with `fakeApi` for each health state, one request per Check, Check all, and no secret field rendered; compare with the prototype's Settings screen (manual) (spec: Settings providers)
- [ ] 7.2 Implement `src/components/WritingOptionsForm.tsx` (+ CSS) with the six fields and the optional `base`/`mark`/`baseLabel` markers and Reset per field, as in design.md; verify `WritingOptionsForm.test.tsx`: a changed field shows the mark, the base text, and Reset restores it; unlisted tone and language values appear as options
- [ ] 7.3 Implement `src/screens/settings/WritingDefaults.tsx`: loads `GET /api/settings`, saves each change with `PUT /api/settings` (number on blur or Enter), "Saved" for 1.5 s, server error shown on the field and the old value restored; verify `WritingDefaults.test.tsx`; compare with the prototype's Writing defaults panel (manual) (spec: Writing defaults)
- [ ] 7.4 Implement `src/screens/settings/SecuritySection.tsx`: session line, Sign out (`POST /api/logout`, then lock), the method `none` text without Sign out (and App never locks in that case), token table with masked `wosarcher_••••` plus last four, empty text, create form disabled when empty, one-time reveal with Copy/Copied and Done, revoke alertdialog then delete and toast; verify `SecuritySection.test.tsx` for reveal shown once, method `none`, Cancel sends nothing, revoke deletes and toasts, sign out locks; compare with the prototype's Security panel and Revoke dialog (manual) (spec: Session and sign out, API tokens)

## 8. Run history

- [ ] 8.1 Implement `src/screens/history/HistoryScreen.tsx` (+ CSS): H1 and count, table with Query (rewrite line with changed writing options), Date, Recipe, Status tag (including Queued and Interrupted), Duration, Cost, row actions; Recipe from `until`, Duration from `duration_s`, Cost from `cost`, and a fork's changes from its `writing` against its parent's row, all from the one `GET /api/runs` response (design.md, Backend fields); verify `HistoryScreen.test.tsx` with a fixture of runs including a fork, failed, cancelled, and running run (running shows "–" for Duration) and that no `GET /api/runs/{id}` is sent; compare with the prototype's History screen (manual) (spec: Run history)
- [ ] 8.2 Add search (`/` focus), Status and Recipe filters, "No runs match" with Clear filters, and the `emptyHistory` state with New run; verify tests for each; compare with the prototype with `emptyHistory` on (manual) (spec: History search and filters, History empty state)
- [ ] 8.3 Add Open (completed to `#/runs/<id>`, others to `#/live/<id>`), Rerun (`api.rerunRun(id)`, then follow the new run and go Live), Delete with Undo (row hidden, `DELETE` after 6 s, Undo restores); verify tests with fake timers for undo and delete (spec: History actions)

## 9. Dev preview

- [ ] 9.1 Implement `src/dev/preview.tsx` and fixtures in `src/test/fixtures/` for `login`, `login-wrong`, `login-limited`, History, `emptyHistory`, and Settings, loaded only when `import.meta.env.DEV`; verify a test that the production bundle (`vite build`) contains no `preview` module name

## 10. Documentation and gate

- [ ] 10.1 Update docs/design.md "Frontend design": hash routes, the two vendored stylesheets and CSS modules with `data-state` variants, the data layer (ApiClient, RunEvents, reducer), and the dev preview; verify the section describes the code as built
- [ ] 10.2 Verify `scripts/check --full` passes and `openspec validate frontend-shell --strict` passes

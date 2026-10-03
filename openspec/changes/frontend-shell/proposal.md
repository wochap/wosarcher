# Proposal

## Why

The server, events, and authentication exist, but there is no browser UI:
people can only use the CLI, and the server's WebSocket stream has no
reader. The design bundle in `design/` defines the UI. This change builds
the frame every screen lives in (styles, data layer, navigation, sign-in)
plus the screens that are not about a single run (Settings, History), so
the next change (`frontend-run`) only has to build the run screens.

## What Changes

- New `web/` project: Vite, React, TypeScript, pnpm, Biome, Vitest. Scripts
  `dev`, `build`, `test`, `gen:types`, `check:types`.
- Styling: the Nocturne `styles.css` vendored into `web/src/vendor/` (its
  Google Fonts import removed) plus the prototype's token additions (muted,
  faint, line, mono, danger, warn), light theme block, scrollbar, and
  keyframes as a second vendored global stylesheet. Inter and Phosphor
  icons are bundled; nothing loads from a CDN.
- Generated TypeScript types from `wosarcher schema` (JSON Schema of the
  contracts, the event models, and the server's request and response
  models) with json-schema-to-typescript, and a drift check run by
  `scripts/check --full`.
- Data layer: a typed API client (cookie session, JSON errors, 401 opens
  the sign-in screen), a run event client over `WS /api/runs/{id}/events` that
  reconnects with `?since=<last seq>`, and a pure reducer that turns the
  event stream into run view state (dedupe by `seq`, phases, sub-queries,
  sources, passages, report text, costs, connection state).
- App shell matching the prototype: desktop sidebar (184px), phone top bar
  below 720px, theme toggle (first visit follows `prefers-color-scheme`,
  then remembered), keyboard shortcuts, toast, dialogs, hash routes.
- Screens: Sign in (`login`, `login-wrong`, `login-limited`), Settings
  (provider health cards, profile line, writing defaults with autosave,
  Security: session, sign out, API tokens with one-time reveal and revoke),
  Run history (table, search, status and recipe filters, open, rerun,
  delete with undo, empty states).
- Placeholder New run, Live run, and Report screens that only show their
  title; `frontend-run` replaces them.
- The built UI goes to `web/dist`, which `server-api` serves at `/`.
- The name is "wosarcher" everywhere the prototype says "Sift".

## Non-goals

- New run, Live run, Report, Versions, citation tooltips: `frontend-run`.
- No router, state-management, CSS framework, or component library
  dependency (no Tailwind, no shadcn/ui).
- No server-side rendering, no service worker, no offline mode.
- No changes to backend contracts: the run summary fields (`until`,
  `duration_s`, `cost`, `fork_from`, `writing`) and `POST
  /api/runs/{id}/rerun` come from `server-api`.
- No account management beyond the single admin password (set from the
  CLI, not the UI).

## Capabilities

### New Capabilities

- `web-shell`: the browser application frame: build and styling rules,
  generated types, API and event clients, the run event reducer, navigation
  and theme, sign-in, Settings, and Run history.

### Modified Capabilities

None.

## Impact

- New code: `web/` (package.json, biome.json, tsconfig, vite.config.ts,
  `src/`), generated `web/src/api/generated.ts`.
- Backend: none. `server-api` already serves `server.static_dir`
  (default `web/dist`) at `/` with an `index.html` fallback, and every API
  route and the WebSocket live under `/api`.
- `scripts/check`: `--full` also runs `pnpm --dir web run check:types`.
- New frontend dependencies: react, react-dom, react-markdown,
  @phosphor-icons/react, @fontsource/inter; dev: vite,
  @vitejs/plugin-react, typescript, @biomejs/biome, vitest, jsdom,
  @testing-library/react, @testing-library/user-event,
  json-schema-to-typescript.
- Depends on `server-api` (endpoints, WS events, server response models in
  `wosarcher schema`) and `admin-auth` (login, session, tokens).
- docs/design.md sections implemented: Tech stack (frontend), Frontend
  design, Frontend decisions (name, theme, device label, sample data),
  Server (served build, settings, profiles, health, tokens, runs list),
  Authentication (browser session, WebSocket cookie, sign-in limits as
  shown to the user), Events (client side: replay with `since`, snapshot).
- docs/design.md changes: Frontend design gains the routing, data-layer,
  and stylesheet layout decisions; docs/frontend-inventory.md is unchanged.

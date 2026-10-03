# Design

## Context

Before this change the repository has the backend from changes 1 to 10:
`wosarcher run`/`fork`, the run store and `events.jsonl`, the FastAPI server
under `/api` (`server-api`; it also serves `server.static_dir`, default
`web/dist`, at `/` with an `index.html` fallback, port 8765) and the
WebSocket event stream, admin authentication (`admin-auth`: password login,
signed session cookie, API tokens that work only from a browser session;
with no password set the server binds loopback and every request counts
as authenticated with method `none`),
and `wosarcher schema`, which prints one JSON Schema document for the
contracts, the event models, and the server's request and response models.
There is no `web/` directory; `scripts/check-frontend` skips the frontend
until `web/package.json` exists, then runs Biome and the design-token rules
(no raw hex colors, no font families outside variables; `web/src/vendor/`
is exempt). `scripts/check --full` adds `tsc --noEmit` and `pnpm run test`.

The design source is `design/project/Sift Research.dc.html`; all styling
there is inline and computed in JS. docs/frontend-inventory.md lists its
metrics. See proposal.md for scope.

## Goals / Non-Goals

**Goals:**

- A frontend a person can read file by file: one screen per directory,
  components under 200 lines, CSS modules next to them.
- One data path for every run screen: events in, one pure reducer, one view
  state out. The same reducer serves live runs, reconnects, and finished
  runs (a finished run is its replayed event log).
- Screens testable without a server, and viewable without a server for the
  manual comparison with the prototype.

**Non-Goals:**

- Client-side caching beyond what a screen holds while open.
- Internationalisation of the UI text (English only, as in the prototype).
- Supporting browsers without CSS `color-mix()` (the design needs it).

## Decisions

### Layout of `web/`

```
web/
  package.json  biome.json  tsconfig.json  vite.config.ts  index.html
  scripts/gen-types.mjs        # wosarcher schema -> src/api/generated.ts (--check: drift)
  src/
    main.tsx                   # fonts, global CSS, <App/>
    vendor/nocturne.css        # Nocturne styles.css, verbatim minus the Google Fonts @import
    vendor/prototype.css       # the prototype's .sx additions, rescoped to :root
    app.css                    # html/body/#root sizing, base font size, a.link rules
    api/generated.ts           # generated, not edited, excluded from Biome
    api/client.ts              # ApiClient interface + httpApi()
    api/events.ts              # RunEvents: WebSocket with reconnect
    run/reducer.ts             # runReducer(state, event) -> state (pure)
    run/useRun.ts              # hook: RunEvents + reducer for one run id
    app/                       # App, routes, Shell (nav), theme, toast, overlays, keys
    components/                # Seg, Tag, StatusTag, Dialog, Toast, WritingOptionsForm, Icon helpers
    screens/login/ screens/settings/ screens/history/
    screens/new/ screens/live/ screens/report/   # placeholders here; frontend-run fills them
    dev/preview.tsx            # dev-only scenario preview (see below)
    test/                      # fakes (FakeWebSocket, fakeApi) and event fixtures
```

Biome 2 config: `files.includes` is `["**", "!dist", "!src/vendor",
"!src/api/generated.ts"]`, formatter indent 2 spaces, line width 100,
recommended lint rules.

### Stylesheets: two vendored sheets plus CSS modules

`vendor/nocturne.css` is the bundle's `styles.css` copied verbatim except
line 2 (the Google Fonts `@import`), which is removed with a comment saying
Inter comes from `@fontsource/inter`. `vendor/prototype.css` transcribes the
prototype's `<style>` block (lines 17 to 26) with `.sx` replaced by `:root`
and `.sx[data-theme=light]` by `:root[data-theme="light"]`; the `.sx .seg`,
`.sx select.input`, scrollbar, and link rules become global rules. Both
live in `vendor/` because the light theme block is raw hex by nature, which
the token check exempts only there. The theme is the `data-theme`
attribute on `<html>`.

Every prototype inline style becomes a CSS module class next to its
component. Values computed in JS in the prototype (status colors, phase
state styles, banner tints, health tints) become variants selected with a
`data-state` (or `data-tone`) attribute, so the CSS lists every variant in
one place and components never build style strings. `style-hover`
attributes become `:hover` rules. Raw px sizes stay as px (the token check
allows them; the prototype uses fixed sizes).

Alternative: CSS-in-JS or inline style objects mirroring the prototype.
Rejected: they hide variants in code and make the token check impossible.

### Fonts and icons

`@fontsource/inter` (weights 400, 500, 600, 700) is imported in `main.tsx`;
Vite bundles the woff2 files. `@phosphor-icons/react` renders inline SVG,
so no icon font is needed; filled icons use `weight="fill"`. Spinning and
pulsing icons get the shared classes `.spin` (`sx-spin .9s linear
infinite`) and `.pulse` from `app.css`. Dependency reason: the prototype
uses Inter and Phosphor; both packages are the official distributions and
keep the build free of CDN requests.

### Routing: URL fragment, no router library

`app/route.ts` (about 40 lines) parses `location.hash` into
`{screen: "new" | "live" | "report" | "history" | "settings", runId?}` and
listens to `hashchange`; `go(route)` sets the hash. Routes: `#/new`,
`#/live`, `#/live/<id>`, `#/runs/<id>` (Report), `#/history`,
`#/settings`; empty or unknown is `#/new`. Fragments never reach the
server, so the app needs no history handling and reloads always load
`index.html`. Alternative: react-router with
history URLs. Rejected: a dependency for five routes.

### State: React state and context, no store library

App-level state lives in `App` with `useReducer` and is passed through
three small contexts: `AuthContext` (locked, reason), `UiContext` (theme,
toast, overlay stack, phone flag), and `ApiContext` (the `ApiClient`).
The followed run (the run "Live run" opens) is App state: set when a run is
started, opened on Live, or, at start, the newest run from `GET /api/runs`
whose status is queued or running. The app keeps the followed run's event
stream open on every screen so the nav dot is live.

Alternative: Zustand or Redux. Rejected: three contexts are enough.

### API client: an interface with an HTTP implementation

`ApiClient` is a TypeScript interface with one method per endpoint
(`listRuns`, `getRun`, `createRun`, `forkRun`, `rerunRun`, `cancelRun`, `deleteRun`,
`getArtifact`, `getSettings`, `putSettings`, `listProfiles`, `health`,
`getSession`, `login`, `logout`, `listTokens`, `createToken`,
`deleteToken`), typed with the generated types. `httpApi(onUnauthorized)`
implements it with `fetch` (`credentials: "same-origin"`, JSON bodies;
`createRun` sends multipart). A non-2xx answer throws `ApiError {status,
message, fields}` built from the server's JSON error body; 401 also calls
`onUnauthorized`, which locks the app. `login` returns a result union
(`ok`, `wrong` with attempts left, `limited` with `retry_after`) instead
of throwing, because those are expected states. Tests and the preview use
`fakeApi(data)` from `src/test/`. Alternative: generated OpenAPI client.
Rejected: another generator and runtime for about 20 calls.

### Event client and reducer

`RunEvents` (`api/events.ts`, plain class) owns one WebSocket to
`${ws|wss}://${location.host}/api/runs/{id}/events?since=N` and reports
`{kind: "event", event}` and `{kind: "conn", state, attempt, replayed}`
to one callback. Connection states: `connecting`, `connected`,
`reconnecting` (attempt N), `replaying`, `closed`. Close codes from
`server-api`: 1000 after a terminal event or a finished run's replay (no
reconnect, state `closed`), 4404 unknown run (no reconnect, `notFound`),
4408 slow client and any other code (reconnect). A reconnect waits 2 s,
calls `api.getRun(id)` (401 locks the app; the WebSocket itself cannot
report 401, the guard closes the handshake with 1008), then connects with
`since` = highest applied logged `seq`; it stays `replaying` until an
event with `seq >= last_seq` from that response arrives (or at once when
`since == last_seq`), and `replayed = last_seq - since`. The WebSocket
constructor is injected so tests use `FakeWebSocket`.

`runReducer(state, event)` is a pure function over the generated event
union with one `case` per event type; `seq <= state.lastSeq` returns the
same state object (dedupe). The live-only events `run.queued`,
`report.delta`, and `report.snapshot` carry the `seq` of the last logged
event, so they skip the dedupe and never move `lastSeq`. The final
`report.snapshot` at the end of the write stage replaces the streamed
text. The view state:

```ts
type RunView = {
  runId: string; lastSeq: number;
  status: "queued"|"running"|"done"|"failed"|"cancelled"|"interrupted";  // interrupted: set from GET /api/runs/{id}
  startedAt?: string; endedAt?: string; failure?: {stage: string; error: string};
  phases: Record<PhaseId, {state: PhaseState; counters: Record<string, number>;
                           device?: string; waitReason?: string}>;
  subQueries: {id: string; text: string; results: number; done: boolean}[];
  sources: Record<string, {sourceId: string; kind: "web"|"file"; title: string; uri: string;
                           state: "found"|"fetched"|"failed"; reason?: string; kept: number}>;
  passages: {queryId: string; scorer: string; threshold: number; items: Passage[]}[];
  report: string; tokensIn: number; tokensOut: number; cost: number;
};
```

`PhaseId` is the nine prototype phases, named as the run-orchestration
stages (the initial search runs inside the `plan` stage, so it needs no
mapping). A phase is `pending` until `resource.waiting` (then `waiting`,
reason "<released stage> unloading", device from the event) or
`stage.started` (then `running`, device from `data.device`), then `done`
(`skipped` kept as a flag), `reused` when `stage.done.copied_from` is set,
`failed`, or, when the run is cancelled while it runs, `cancelled`.
Counters come from `stage.progress` (`done`, `total`, `failed`); tokens
and cost from `stage.done` usage and cost; `run.started` gives profile,
parent, version, and `until`. `useRun(runId)`
combines both and also exposes the connection state for the footer and
banner.

Alternative: keep events in a list and derive everything per render.
Rejected: a 10 000-event run would be re-folded on every delta.

### Generated types and drift check

`scripts/gen-types.mjs` runs `uv run --frozen wosarcher schema` from the
repository root, passes the document to `json-schema-to-typescript`'s
`compile` with `unreachableDefinitions: true` and a banner saying the file
is generated, and writes `src/api/generated.ts`. With `--check` it writes
nothing and exits 1 with "src/api/generated.ts is out of date; run pnpm
--dir web run gen:types" when the output differs. package.json scripts:
`gen:types` and `check:types`; `scripts/check --full` runs `pnpm --dir web
run check:types` after the frontend tests.

### Backend fields this change reads

All through the generated types; names below follow the `server-api`,
`admin-auth`, and `run-orchestration` drafts.

| Source | Fields used |
|---|---|
| `GET /api/runs` item (`RunSummary`) | `run_id`, `query`, `status` (queued, running, done, failed, cancelled, interrupted), `created`, `parent_run_id`, `version`, `fork_from`, `profile`, `sources`, `until`, `writing`, `duration_s`, `cost`, `queue_position` |
| `GET /api/runs/{id}` | the summary plus redacted `request`, `costs`, `last_seq` |
| `GET /api/settings` | `writing`, `sources` (PUT sends both back) |
| `GET /api/profiles` | `name`, `source`, `active` |
| `GET /api/providers/health` (`HealthReport`) | `profile`, `warnings`, `checks[]`: `role`, `provider`, `url`, `model`, `device`, `status` (ok, degraded, down, skipped), `latency_ms`, `detail`; no per-role check, so one request checks every card |
| `POST /api/runs/{id}/rerun` | 201 with `run_id` and `status`; the server copies the original attachments |
| `GET /api/session` (`SessionInfo`) | `method` (cookie, token, none), `since`, `expires`, `token_name` |
| `GET /api/tokens` (`TokenInfo`) | `id`, `name`, `masked`, `created`, `last_used` |
| `POST /api/login` | 200, 401 with `attempts_left`, 429 with `retry_after` (`LoginError`) |
| events | see "Event client and reducer" |

The History screen needs only `GET /api/runs`: Recipe is `until`
(`select` → "context", null → "report"), Duration is `duration_s`
(`m:ss`, "–" when null), Cost is `cost` ("–" when null), and a fork's
writing changes are the fields where its `writing` differs from its
parent's `writing` (the parent's row in the same list; "–" if the parent
was deleted).

### Login states

`LoginScreen` is an overlay (z 40) rendered by `App` when locked, over the
current screen. Its state machine: `idle` → submit → `ok` (unlock),
`wrong` (attempts left), `limited` (`until = now + retry_after`). A 1 s
interval drives the countdown only while limited; at zero the state goes
back to `idle`. The bar width is `remaining / retry_after`.

### Settings writing defaults

`WritingOptionsForm` (in `components/`, reused by New run and the Rewrite
dialog in `frontend-run`) renders the six writing fields in the
prototype's form grid. Props: `value`, `onChange(field, value)`,
optional `base` with `mark` ("overridden" or "changed") and `baseLabel`
("default: " or "was "), `idPrefix`, and `compact` (dialog columns).
Controls: Tone is a wrapping `.seg` of the 11 tones listed in
docs/design.md "Writing options" (a constant in `components/tones.ts`; a
saved value outside the list is added as an extra option); Custom tone
instructions a textarea; Target length a number input (100 to 4000, step
50); Language a select of English, German, French, Spanish, Portuguese,
Japanese, Chinese (Simplified) (values lowercase, an unlisted current value
is added); Citation marker a `.seg` of "[1] Numeric", "¹ Superscript",
"(Author, year)"; Reference style a select of APA, MLA, Chicago, IEEE.
Settings saves each change immediately with `PUT /api/settings` (number field:
on blur or Enter, so typing "800" sends one request).

### History delete with undo

The row is removed from screen state at once; `setTimeout(6000)` sends
`DELETE /api/runs/{id}`; Undo clears the timer and restores the row. Leaving the
screen does not cancel the timer (it lives in App). Closing the tab within
6 s keeps the run, which is the safe failure.

### Dev-only preview

`#/preview/<name>` (only when `import.meta.env.DEV`; the import is behind
that check so production builds drop it) renders the app with `fakeApi`
and a fake event stream from a fixture. This change adds fixtures for
`login`, `login-wrong`, `login-limited`, History (with runs and with
`emptyHistory`), and Settings; `frontend-run` adds the run scenarios. It
exists for the manual comparison with the prototype, which is done by
opening the prototype and the preview side by side in both themes and at
390px and 1440px widths.

### Development server

`vite.config.ts` proxies `/api` (HTTP and WebSocket, `ws: true`) to
`WOSARCHER_DEV_API` (default `http://127.0.0.1:8765`) and rewrites the
`Origin` header to the target, so the `admin-auth` Origin check passes in
development. Production needs nothing: `server-api` serves `web/dist`.

## Risks / Trade-offs

- [Assumed backend fields] → If `server-api` or `admin-auth` names them
  differently, only the generated types and the code reading them change;
  the drift check makes the mismatch a type error, not a runtime bug.
- [Followed run stream open on every screen] → One idle WebSocket per tab.
  Acceptable for a single-user local tool.
- [Hash URLs] → Less pretty than paths. Accepted for zero server routing.
- [Manual visual comparison] → Pixel drift can slip through tests.
  Mitigation: the preview route makes the comparison quick, and every
  frontend task names the scenario to compare.
- [Two vendored stylesheets] → Upstream Nocturne changes need a manual
  re-copy. Accepted; the bundle is a fixed handoff.

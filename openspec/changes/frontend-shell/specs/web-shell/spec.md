# Spec Delta

## Purpose

The browser application frame for wosarcher: how the UI is built, styled,
and served, how it talks to the server and follows a run's event stream,
and the screens that are not about one run (sign-in, Settings, Run
history), all matching the design bundle in `design/`.

## ADDED Requirements

### Requirement: Design source and name
Every screen and state SHALL match `design/project/Sift Research.dc.html`
(the "prototype") in layout, sizes, colors, icons, and text, in the dark
and light themes and in the desktop and phone layouts, except where
docs/design.md "Frontend decisions" overrides it. The product name SHALL be
"wosarcher" wherever the prototype says "Sift", including the brand,
the API token prefix shown in the UI, and browser storage keys. No version
string SHALL be hard-coded.

#### Scenario: Brand in the sidebar
- **WHEN** the app is open on a desktop-width window (any prototype scenario, for example `new`)
- **THEN** the sidebar brand row shows the funnel icon and "wosarcher", and the word "Sift" appears nowhere in the UI

### Requirement: Self-contained assets
The built UI SHALL load its fonts (Inter) and icons (Phosphor) from its own
build output. It SHALL make no request to any origin other than the page's
own origin.

#### Scenario: No external requests
- **WHEN** the built UI is opened and every screen is visited
- **THEN** every network request goes to the page's own origin

### Requirement: Styling uses the design system
Colors, fonts, radii, and shadows SHALL come from the vendored Nocturne
stylesheet and the vendored prototype additions (`--muted`, `--faint`,
`--line`, `--mono`, `--color-danger`, `--color-warn`, the light theme
block, the scrollbar style, and the keyframes `sx-spin`, `sx-pulse`,
`sx-blink`, `sx-shimmer`). Application stylesheets outside the vendored
directory SHALL contain no raw hex colors and no font family other than a
Nocturne or prototype font variable. The UI SHALL NOT use Tailwind or a
third-party component library.

#### Scenario: Token check
- **WHEN** an application stylesheet outside `web/src/vendor/` contains a raw hex color
- **THEN** `scripts/check` fails and names the file and line

### Requirement: Screen URLs and API paths
The UI SHALL be built into `web/dist`, which the server serves at `/`. All
screens SHALL be reached through the URL fragment (`#/new`,
`#/live/<run id>`, `#/runs/<run id>`, `#/history`, `#/settings`).
Reloading the page SHALL keep the current screen. Every request the UI
makes SHALL go to the page's own origin under `/api`.

#### Scenario: Reload keeps the screen
- **WHEN** the user is on `#/history` and reloads the page
- **THEN** the Run history screen is shown again

#### Scenario: Same-origin API
- **WHEN** the UI loads the run list
- **THEN** it requests `/api/runs` on the page's own origin

### Requirement: Generated types
The UI's types for contracts, events, and server requests and responses
SHALL be generated from the output of `wosarcher schema`. A check SHALL fail
when the committed generated types differ from what the current schema
produces.

#### Scenario: Drift detected
- **WHEN** a backend model gains a field and the generated types are not regenerated
- **THEN** `scripts/check --full` fails and names the generated file

### Requirement: Desktop navigation
On windows 720px wide or wider, the app SHALL show the prototype's sidebar
(any scenario except `login*`): 184px wide, the brand row, the items New run
(Alt 1), Live run (Alt 2), History (Alt 3), and Settings (Alt 4) with
their Phosphor icons and shortcut hints, and at the bottom the theme toggle
and the WebSocket origin of the page (for example `ws://localhost:8765`).
The item of the current screen SHALL be highlighted and marked
`aria-current="page"`; Live run SHALL also be highlighted on the Report
screen. Live run SHALL show a pulsing accent dot while the followed run is
queued or running; Settings SHALL show a static warn dot while any
provider's last health result is not healthy.

#### Scenario: Active item
- **WHEN** the user is on the Settings screen
- **THEN** the Settings item has the accent tint and `aria-current="page"`, and no other item does

#### Scenario: Live dot
- **WHEN** the followed run is running (scenario `live`)
- **THEN** the Live run item shows the pulsing accent dot

#### Scenario: Provider warning dot
- **WHEN** the last health check reported the search provider as slow
- **THEN** the Settings item shows the warn dot

### Requirement: Phone navigation
Below 720px wide, the app SHALL replace the sidebar with the prototype's
phone top bar: brand icon and name, the four items as 44px icon buttons
with accessible labels and the same dots, and a 44px theme toggle. Page
padding, form columns, and other phone metrics SHALL follow the prototype's
phone values.

#### Scenario: Narrow window
- **WHEN** the window is 390px wide (prototype `device=phone`)
- **THEN** the top bar is shown, the sidebar is not, and each nav button has an accessible label such as "History"

### Requirement: Theme
The app SHALL offer a dark and a light theme matching the prototype's
`theme` values. On the first visit the theme SHALL follow the browser's
`prefers-color-scheme`. The toggle ("Light theme" with a sun icon in dark,
"Dark theme" with a moon icon in light) SHALL switch the theme, and the
choice SHALL be remembered in the browser and used on later visits.

#### Scenario: First visit in a light-mode browser
- **WHEN** a browser that prefers a light color scheme opens the app for the first time
- **THEN** the light theme is used

#### Scenario: Choice remembered
- **WHEN** the user switches to the dark theme and reloads the page
- **THEN** the dark theme is used, whatever the browser prefers

### Requirement: Keyboard shortcuts
Alt+1 to Alt+4 SHALL switch to New run, Live run, History, and Settings
(by physical key, so they work on any keyboard layout). Escape SHALL close,
in this order, the open confirmation dialog, then the open form dialog,
then an open tooltip. `/` SHALL focus the History search when the History
screen is shown and focus is not in a text field. While the sign-in screen
is shown, no shortcut SHALL act.

#### Scenario: Switch screens
- **WHEN** the user presses Alt+3 outside a text field
- **THEN** the Run history screen is shown

#### Scenario: Locked
- **WHEN** the sign-in screen is shown and the user presses Alt+4
- **THEN** nothing changes

### Requirement: Sign in
When the server answers any request with 401, or the session check at
start finds no session, the app SHALL show the prototype's sign-in screen
(scenario `login`) over the current screen: brand, "Sign in", "Enter the
password for this wosarcher instance.", a password field with a show and
hide toggle, a "Sign in" button disabled while the field is empty, and the
page's host below. Submitting SHALL send the password to `POST /api/login`. On
success the sign-in screen SHALL close and the user SHALL stay on the screen
they were on.

#### Scenario: Successful sign-in
- **WHEN** the user enters the correct password and presses Enter
- **THEN** the sign-in screen closes and the screen behind it is usable

#### Scenario: Session expired
- **WHEN** the user is on Run history and a request returns 401
- **THEN** the sign-in screen is shown, and after signing in the user is on Run history

### Requirement: Wrong password
When `POST /api/login` rejects the password, the sign-in screen SHALL show the
prototype's `login-wrong` state: the danger alert "Wrong password" with
"N attempts left before sign-in pauses." using the attempts left from the
server, the field border in the danger color with `aria-invalid="true"`,
an emptied field, and focus back in the field.

#### Scenario: Three attempts left
- **WHEN** the server rejects the password and reports 3 attempts left
- **THEN** the alert reads "Wrong password" and "3 attempts left before sign-in pauses." and the field is marked invalid

### Requirement: Sign-in paused
When `POST /api/login` answers that sign-in is rate limited, the sign-in screen
SHALL show the prototype's `login-limited` state for the `retry_after`
seconds from the server: the warn alert "Too many attempts" with "Sign-in
is paused. Try again in m:ss.", a 2px warn bar that shrinks to zero over the
wait, a disabled field, and a disabled button reading "Try again in N s"
with a lock icon. The countdown SHALL update every second. When it reaches
zero, the alert SHALL disappear and the field and button SHALL be enabled.

#### Scenario: Countdown
- **WHEN** the server answers with `retry_after` 30
- **THEN** the button reads "Try again in 30 s", and one second later "Try again in 29 s"

#### Scenario: Pause ends
- **WHEN** the countdown reaches zero
- **THEN** the alert is gone and the user can type and submit again

### Requirement: Run event stream
To follow a run, the app SHALL open `WS /api/runs/{id}/events?since=<seq>`
on the page's own origin, starting at `since=0`. When the connection closes
before a terminal event, with any code other than 1000 or 4404, the app
SHALL try to reconnect every 2 seconds, counting attempts. Before each
attempt it SHALL read `GET /api/runs/{id}` (a 401 shows the sign-in
screen) and then connect with `since` set to the highest logged `seq` it
has applied; the events up to that response's `last_seq` SHALL be counted
as replayed, and the connection is "replaying" until they have arrived.
Logged events SHALL be applied in `seq` order and a logged event whose
`seq` was already applied SHALL be ignored. The live-only events
`run.queued`, `report.delta`, and `report.snapshot` SHALL always be applied
and SHALL NOT change the highest applied `seq`. `report.delta` SHALL append
to the report text and `report.snapshot` SHALL replace it. After `run.done`,
`run.failed`, or `run.cancelled`, or a close with code 1000, the app SHALL
not reconnect; a close with 4404 SHALL show "Run not found".

#### Scenario: Replay after a drop
- **WHEN** the connection drops after the app applied seq 351 and the next attempt succeeds
- **THEN** the app connects with `since=351`, applies the replayed events once each, and reports how many were replayed

#### Scenario: Duplicate event
- **WHEN** an event with an already applied `seq` arrives
- **THEN** the run view state does not change

#### Scenario: Snapshot replaces streamed text
- **WHEN** the report text so far is "Hello" and a `report.snapshot` with "Hello world" arrives
- **THEN** the report text is "Hello world"

### Requirement: Run view state
The app SHALL derive one run view state from the applied events, used by
every run screen: run status (queued, running, done, failed, cancelled)
and the failed stage with its error text; for each of the nine phases (Plan,
Search, Fetch, Load, Chunk, Prefilter, Score, Select, Write) a state
(pending, waiting, running, done, reused, failed, cancelled), its counters,
its device label, and its wait reason; the sub-queries; the sources with
their fetch state, failure reason, and kept count; the scored passages per
query with the scorer and display threshold; the report text; prompt and
completion tokens and cost summed over `stage.done`; and the run start and
end times. A phase SHALL be `waiting` between `resource.waiting` and its
`stage.started`, with the wait reason "<released stage> unloading" from
the event, and `running` after `stage.started` until `stage.done` or
`stage.failed`. A `stage.done` with `copied_from` SHALL make the phase
`reused`, and one with `skipped` SHALL make it done and skipped. The
device label SHALL come from `stage.started`. The run status SHALL be
`interrupted` when the server reports it so. The initial search runs
inside the `plan` stage and SHALL count as part of Plan.

#### Scenario: Waiting for a device
- **WHEN** `resource.waiting` arrives for the score stage with released stage `prefilter`, and `stage.started` for score has not
- **THEN** the Score phase state is `waiting` with the reason "prefilter unloading"

#### Scenario: Copied stage of a fork
- **WHEN** `stage.done` for search arrives with `copied_from` = `r1`
- **THEN** the Search phase is `reused` and names `r1`

#### Scenario: Failure
- **WHEN** `stage.failed` and then `run.failed` arrive for the score stage
- **THEN** the run status is failed, the Score phase is `failed`, and the error text is kept

#### Scenario: Costs
- **WHEN** two `stage.done` events report 1200 and 38400 prompt tokens
- **THEN** the run's prompt token total is 39600

### Requirement: Settings providers
The Settings screen of the prototype (no dedicated scenario; reached with
Alt+4 from any scenario) SHALL show the H1 "Settings" with a "Check all
providers" button, the active profile line, and a "Providers" grid with one
card per configured provider role (Search, Fetch, Embeddings, Scorer, LLM)
showing the provider name, URL, and model from
`GET /api/providers/health`. Each card's health strip SHALL show the last
result: `ok` as "Healthy · N ms", `degraded` as "Slow · N ms" with the
detail, `down` as "Unreachable · <detail>", and `skipped` as "Skipped ·
<detail>", with the matching prototype icon and tint, and how long ago the
result arrived. The server checks all providers of the profile at once, so
"Check" on a card and "Check all providers" SHALL both run one health
request; while it runs, the cards SHALL show "Checking…" with the spinning
dashed circle and the Check buttons SHALL be disabled. The profile line
SHALL name the checked profile and the device labels its providers use.
Secrets SHALL never be shown.

#### Scenario: Slow provider
- **WHEN** the health result for search is `degraded` at 1,840 ms
- **THEN** the Search card shows the warn icon and "Slow · 1,840 ms" on the warn tint

#### Scenario: Check all
- **WHEN** the user presses "Check all providers"
- **THEN** every card shows "Checking…" until the new results arrive

### Requirement: Writing defaults
The Settings screen SHALL show the "Writing defaults" panel with the fields
Tone, Custom tone instructions, Target length (100 to 4000 words, step 50),
Language, Citation marker, and Reference style, loaded from
`GET /api/settings`. Each change SHALL be saved with `PUT /api/settings` without a
save button, and a "Saved" mark with a check SHALL show for 1.5 seconds
after the server accepts it. When the server rejects a value, the field
SHALL show the server's error and the previous value SHALL be restored.

#### Scenario: Autosave
- **WHEN** the user changes Target length to 800
- **THEN** `PUT /api/settings` is sent with `words` 800 and "Saved" appears

#### Scenario: Rejected value
- **WHEN** the server rejects a change
- **THEN** the field shows the error and the earlier value is shown again

### Requirement: Session and sign out
The Security panel SHALL show "Signed in on this browser since <date,
time>." from `GET /api/session` and a "Sign out" button. Sign out SHALL call
`POST /api/logout` and show the sign-in screen (scenario `login`). When the
session method is `none` (no password is set), the panel SHALL instead show
"No password is set; the server accepts local connections only." and no
Sign out button, and the app SHALL never show the sign-in screen.

#### Scenario: Sign out
- **WHEN** the user presses "Sign out"
- **THEN** the session is ended on the server and the sign-in screen is shown

#### Scenario: No password set
- **WHEN** `GET /api/session` reports method `none`
- **THEN** the Security panel says no password is set and has no Sign out button

### Requirement: API tokens
The Security panel SHALL list the API tokens from `GET /api/tokens` in a table
(name, the masked token from the server, `wosarcher_••••` plus the last four characters, created,
last used or "Never", and a Revoke action), or "No tokens. The local API
only accepts requests from a signed-in browser." when there are none. The
create form SHALL be disabled while the name is empty. Creating a token
SHALL show the prototype's one-time reveal: "Token “<name>” created", the
full token selectable in one click, a Copy button that changes to "Copied",
the warning "Copy it now. It won't be shown again.", and "Done", which hides
it for good. Revoke SHALL first ask in an alert dialog "Revoke “<name>”?"
and only then call `DELETE /api/tokens/{id}`, remove the row, and show the
toast "Token “<name>” revoked".

#### Scenario: One-time reveal
- **WHEN** the user creates a token named "ci-runner"
- **THEN** the full token is shown once with Copy, and after "Done" or a reload it is no longer shown anywhere

#### Scenario: Revoke needs confirmation
- **WHEN** the user presses Revoke and then Cancel (or Escape)
- **THEN** no request is sent and the token is still listed

### Requirement: Run history
The Run history screen of the prototype (no dedicated scenario; reached
with Alt+3) SHALL list runs from `GET /api/runs`, newest first, with the H1
"Run history" and the run count, in a table with Query, Date, Recipe
(`report`, or `context` for runs whose `until` is `select`), Status,
Duration (`m:ss` from `duration_s`, "–" while it is null), Cost (`$` with
three decimals from `cost`, "–" while it is null), and the row actions
Open, Rerun, and Delete. A fork SHALL show under its query "↳ rewrite of
<parent id> · <writing changes>", where the changes are the writing
options in which the fork's `writing` differs from its parent's. Every
column SHALL come from the `GET /api/runs` response, with no request per
row. Status tags SHALL use the prototype's
icons and tints for completed (`done`), running (spinning; also `queued`,
labelled "Queued"), failed, and cancelled; `interrupted` SHALL use the
failed style with the label "Interrupted", and the Failed filter SHALL
include it.

#### Scenario: Rewrite row
- **WHEN** a run is a fork of `r_7f3a` with tone and length changed
- **THEN** its row shows "rewrite of r_7f3a" with the changed options

#### Scenario: Duration and cost
- **WHEN** a finished run has `duration_s = 125` and `cost = 0.012`
- **THEN** its row shows "2:05" and "$0.012"

### Requirement: History search and filters
The search field SHALL filter rows by a case-insensitive substring of the
query, together with the Status filter (All, Completed, Failed, Cancelled)
and the Recipe filter (Any recipe, report, context). When filters hide
every row, the screen SHALL show "No runs match" with a "Clear filters"
button that resets all three.

#### Scenario: No match
- **WHEN** the user searches for a word no query contains
- **THEN** "No runs match" and "Clear filters" are shown

### Requirement: History empty state
When there are no runs, the Run history screen SHALL show the prototype's
`emptyHistory` state: the clock icon, "No runs yet", "Finished, failed and
cancelled runs are kept here with their reports.", and a "New run" button.

#### Scenario: First use
- **WHEN** `GET /api/runs` returns no runs
- **THEN** "No runs yet" and the "New run" button are shown

### Requirement: History actions
Open SHALL show the Report screen for a completed run and the Live run
screen for any other run. Rerun SHALL start a new run with the same request and
attachments through `POST /api/runs/{id}/rerun` and show it on the Live
run screen. Delete SHALL hide the row at once and
show the toast "Run deleted" with Undo for 6 seconds; the run SHALL be
deleted on the server only when the toast expires without Undo, and Undo
SHALL restore the row.

#### Scenario: Rerun
- **WHEN** the user presses Rerun on a run that had attachments
- **THEN** `POST /api/runs/{id}/rerun` is sent and the new run is shown on the Live run screen

#### Scenario: Undo delete
- **WHEN** the user deletes a run and presses Undo within 6 seconds
- **THEN** the row is back and no delete request was sent

#### Scenario: Delete
- **WHEN** the user deletes a run and waits 6 seconds
- **THEN** `DELETE /api/runs/{id}` is sent

### Requirement: Toasts
Confirmations SHALL appear as the prototype's toast: centred 52px above the
bottom edge, a check icon and the message, visible for 2.2 seconds, or 6
seconds when it offers Undo. A new toast SHALL replace the current one.

#### Scenario: Replace
- **WHEN** a toast is visible and another action shows a toast
- **THEN** only the new toast is visible

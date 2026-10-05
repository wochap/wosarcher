# web-shell Specification

## Purpose

The browser application frame for wosarcher: how the UI is built, styled,
and served, how it talks to the server and follows a run's event stream,
and the screens that are not about one run (sign-in, Settings, Run
history), all matching the design bundle in `design/`.

## Requirements

### Requirement: Design source and name
Every screen and state SHALL match `design/project/wosarcher.dc.html`
(the "prototype") in layout, sizes, colors, icons, and text, in the dark
and light themes and in the desktop and phone layouts, except where
docs/design.md "Frontend decisions" overrides it. The product name SHALL be
"wosarcher" everywhere, including the brand, the API token prefix shown in
the UI, and browser storage keys. No version string SHALL be hard-coded.
The prototype's `help` scenario specifies the inline help component and
is not a screen of the app.

#### Scenario: Brand in the sidebar
- **WHEN** the app is open on a desktop-width window (any prototype scenario, for example `new`)
- **THEN** the sidebar brand row shows the funnel icon and "wosarcher" with no version string, and the word "Sift" appears nowhere in the UI

### Requirement: Self-contained assets
The built UI SHALL load its fonts (Inter) and icons (Phosphor) from its own
build output. It SHALL make no request to any origin other than the page's
own origin.

#### Scenario: No external requests
- **WHEN** the built UI is opened and every screen is visited
- **THEN** every network request goes to the page's own origin

### Requirement: Styling uses the design system
Colors, fonts, radii, and shadows SHALL come from the vendored Nocturne
stylesheet and the vendored prototype additions (`--wa-ring`, `--muted`,
`--faint`, `--line`, `--mono`, `--color-danger`, `--color-warn`, the light
theme block, the scrollbar style, and the keyframes `sx-spin`, `sx-pulse`,
`sx-blink`, `sx-shimmer`). `--wa-ring` SHALL be `#9397ab` in the dark
theme and `#c9cddd` in the light theme. Application stylesheets outside
the vendored directory SHALL contain no raw hex colors and no font family
other than a Nocturne or prototype font variable. The UI SHALL NOT use
Tailwind or a third-party component library.

#### Scenario: Token check
- **WHEN** an application stylesheet outside `web/src/vendor/` contains a raw hex color
- **THEN** `scripts/check` fails and names the file and line

#### Scenario: Help arrow ring in both themes
- **WHEN** a help tooltip is open in the light theme (prototype `help` scenario, figure B, `theme=light`)
- **THEN** its arrow's border uses `--wa-ring`, which resolves to `#c9cddd`

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
in this order, an open help tooltip, then the open confirmation dialog,
then the open form dialog, then an open citation tooltip; one press closes
only the first of these that is open. `/` SHALL focus the History search
when the History screen is shown and focus is not in a text field. While
the sign-in screen is shown, no shortcut SHALL act.

#### Scenario: Switch screens
- **WHEN** the user presses Alt+3 outside a text field
- **THEN** the Run history screen is shown

#### Scenario: Locked
- **WHEN** the sign-in screen is shown and the user presses Alt+4
- **THEN** nothing changes

#### Scenario: Help closes before the dialog
- **WHEN** the Rewrite dialog is open with the help tooltip of its Tone field open, and the user presses Escape
- **THEN** the help tooltip closes and the dialog stays open; a second Escape closes the dialog

### Requirement: Sign in
When the server answers any request with 401, or the session check at
start finds no session, the app SHALL show the prototype's sign-in screen
(scenario `login`) over the current screen: brand, "Sign in", "Enter the
password for this wosarcher instance.", a password field with a show and
hide toggle, a "Sign in" button disabled while the field is empty, and the
page's host below. Submitting SHALL send the password to `POST /api/login`. On
success the sign-in screen SHALL close and the user SHALL stay on the screen
they were on. When no run is followed yet, the app SHALL then follow the
newest queued or running run from `GET /api/runs`, as it does after a
successful session check at start.

#### Scenario: Successful sign-in
- **WHEN** the user enters the correct password and presses Enter
- **THEN** the sign-in screen closes and the screen behind it is usable

#### Scenario: Session expired
- **WHEN** the user is on Run history and a request returns 401
- **THEN** the sign-in screen is shown, and after signing in the user is on Run history

#### Scenario: Run in progress at sign-in
- **WHEN** the app starts without a session while a run is running, and the user signs in
- **THEN** Live run (Alt+2) shows that run, not "No run in progress", and the Live run item shows the pulsing dot

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
SHALL try to reconnect, counting attempts, after 2 seconds for the first
attempt and twice the previous wait for each later one, at most 30
seconds; the wait SHALL return to 2 seconds once a socket opens. Before
each attempt it SHALL read `GET /api/runs/{id}` (a 401 shows the sign-in
screen) and apply the run status from it (see "Run status from the
server"); a 404 SHALL stop reconnecting and show "Run not found"; a run
that has ended SHALL not be reconnected when the app has already applied
its `last_seq` or the connection is "unavailable". Otherwise it SHALL connect with `since` set to the highest
logged `seq` it has applied. The connection SHALL become "replaying" only
once the new socket has opened, with the events up to that response's
`last_seq` counted as replayed, and stays "replaying" until they have
arrived. After three attempts in a row whose socket closed without
opening, the connection SHALL be "unavailable": the app keeps trying every
30 seconds, and leaves "unavailable" when a socket opens. Logged events
SHALL be applied in `seq` order and a logged event whose `seq` was already
applied SHALL be ignored, except that `run.done`, `run.failed`, and
`run.cancelled` SHALL be applied whatever their `seq`; one whose `seq` is
not above the highest applied `seq` SHALL NOT change it. The live-only events `run.queued`,
`report.delta`, and `report.snapshot` SHALL always be applied and SHALL NOT
change the highest applied `seq`. `report.delta` SHALL append to the report
text and `report.snapshot` SHALL replace it. After `run.done`,
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

#### Scenario: Cancelled while queued
- **WHEN** the app has applied no logged event and `run.cancelled` arrives with seq 0
- **THEN** the run status is cancelled and the highest applied `seq` stays 0

#### Scenario: Handshake keeps failing
- **WHEN** the socket closes with code 1006 without opening on the first connection and on the next three attempts
- **THEN** the attempts wait 2, 4, and 8 seconds, the connection is never "replaying", and after the third failed attempt it is "unavailable"

#### Scenario: Run deleted while reconnecting
- **WHEN** `GET /api/runs/{id}` answers 404 before an attempt
- **THEN** no further attempt is made and "Run not found" is shown

### Requirement: Run status from the server
When it starts following a run, before each reconnect attempt, and when a
cancel request answers 409, the app SHALL read the run's summary
(`GET /api/runs/{id}`, or the `status` in the 409 body) and, when it says
the run ended (`done`, `failed`, `cancelled`, or `interrupted`) while the
run view state is still queued or running, SHALL set the run status from
it; for `failed` the failed stage and error text SHALL come from the
summary's `end_stage` and `error`, and for `cancelled` the stage from
`end_stage`. Once the run status is ended, no later event other than a
terminal event SHALL make it queued or running again. The run status SHALL
be correct after a page reload even when the event socket never opens.

#### Scenario: Failed run, socket never opens
- **WHEN** the app follows a run whose summary has `status = "failed"`, `end_stage = "fetch"`, and `error = "no output"`, and every socket closes without opening
- **THEN** the run status is failed with the Fetch phase failed and the error "no output", and the Live run item shows no pulsing dot

#### Scenario: Replay after the summary
- **WHEN** the summary has set the status to failed and replayed events `run.started` and `stage.started` arrive afterwards
- **THEN** the run status stays failed

### Requirement: Run view state
The app SHALL derive one run view state from the applied events, used by
every run screen: run status (queued, running, done, failed, cancelled)
and the failed stage with its error text; for each of the nine phases (Plan,
Search, Fetch, Load, Chunk, Prefilter, Score, Select, Write) a state
(pending, waiting, running, done, reused, failed, cancelled), its counters,
its device label, its wait reason, its configured provider, the provider
that ran, and its warnings; the sub-queries, and which of them skipped
prefilter ranking; the sources with their fetch state, failure reason, and
kept count; the scored passages per query with the scorer and display
threshold; the report text; prompt and completion tokens and cost summed
over `stage.done`; and the run start and end times. A phase SHALL be
`waiting` between `resource.waiting` and its `stage.started`, with the wait
reason "<released stage> unloading" from the event, and `running` after
`stage.started` until `stage.done` or `stage.failed`. A `stage.done` with
`copied_from` SHALL make the phase `reused`, and one with `skipped` SHALL
make it done and skipped. The device label and the configured provider
SHALL come from `stage.started`; the provider that ran, the warnings, and
the passthrough sub-queries SHALL come from `stage.done`. A phase is a
fallback when the provider that ran names a different method (the part
before `:`) than the configured provider. The run status SHALL be
`interrupted` when the server reports it so. The initial search, when it
runs, runs inside the `plan` stage and SHALL count as part of Plan; a search
for `q0` made by the search stage SHALL count as part of Search.

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

#### Scenario: Prefilter fallback
- **WHEN** `stage.started` for prefilter carries `embeddings:bge-small-en-v1.5` and `stage.done` carries `bm25`
- **THEN** the Prefilter phase has the configured provider `embeddings:bge-small-en-v1.5`, the provider that ran `bm25`, and is a fallback

#### Scenario: Same method, model kept
- **WHEN** `stage.started` for score carries `rerank:bge-reranker` and `stage.done` carries `rerank`
- **THEN** the Score phase is not a fallback


#### Scenario: Topic searched in Search
- **WHEN** a long query skipped the initial search and `hit.found` events arrive for `q0` after `stage.started` for search
- **THEN** they count toward the Search phase, and the Plan phase shows no hits

### Requirement: Settings providers
The Settings screen of the prototype (`design/project/wosarcher.dc.html`, no
dedicated scenario; reached with Alt+4 from any scenario) SHALL show the H1
"Settings" with a "Check all providers" button, the profile line, the GPU
policy line, the "Providers" heading followed by the note "Checked only
when you click, so idle GPU servers stay asleep.", and a grid with one card
per configured provider block from `GET /api/providers/health`, in the
order the server lists them, titled by role: `search` "Search", `fetch`
"Fetch", `prefilter` "Embeddings" when its provider is `embeddings` and
"Prefilter" otherwise (for example `bm25` or `none`), `score` "Scorer",
`llm` "LLM" (any other block name capitalised). Each card SHALL show the
provider name, a "Check" button labelled for screen readers "Check <role>
provider", and a list with the prototype's 84px label column: Base URL,
Model, Device (the device label, or "–"), and Unload (`none`,
`llama-swap`, or `ollama`, the provider's `release`).

Opening Settings SHALL NOT probe any provider: the screen reads
`GET /api/providers/health`, which answers from the server's stored
results. Each card's health strip SHALL follow the prototype: `unchecked`
as "Not checked yet" with the faint dashed circle on a dashed, untinted
strip; `ok` as "OK · checked <ago>" with the latency ("N ms") as the detail
line; `degraded` as "Slow · checked <ago>" on the warn tint with "N ms,
limit 1,000 ms" (or the server's detail when the latency is within the
limit) as the detail line; `down` as "Down · checked <ago>" on the danger
tint with the error detail in the mono font; and `skipped` as "Skipped ·
<detail>". <ago> is "just now" under 10 s, "N s ago" under a minute, and
otherwise "N m ago", computed from the check's `checked_at` and updated
while the screen is open.

"Check" on a card SHALL post a health check for that card's block only;
while it runs, that card SHALL show "Checking…" with the spinning icon and
its Check button SHALL be disabled, and other cards SHALL stay as they
are. "Check all providers" SHALL post one health check for every block;
while it runs, every card SHALL show "Checking…", every Check button and
"Check all providers" SHALL be disabled. A failed check request SHALL show
its error above the grid and leave the strips with their previous results.

The profile line SHALL read "Active profile <name> · <description>" with
the muted CPU icon, the name in the mono font, and the description of
that profile from `GET /api/profiles`; the name is the profile of the
health report, and " · <description>" is left out when the description is
empty. The GPU policy line SHALL show "GPU policy", a segmented control
with Shared and Exclusive in which the report's `gpu_policy` is selected
and both options are disabled, and the text "Each model unloads before the
next one loads on <devices>." for exclusive or "All models stay loaded on
<devices>." for shared, where <devices> are the distinct device labels of
the `prefilter`, `score`, and `llm` providers joined with ", " (without
" on <devices>" when none has a device label). Secrets SHALL never be
shown.

#### Scenario: Opening Settings sends no check
- **WHEN** the user opens Settings
- **THEN** the app requests `GET /api/providers/health` and posts no health check

#### Scenario: Not checked yet
- **WHEN** the health report has the score block `unchecked`
- **THEN** the Scorer card shows "Not checked yet" with the dashed strip

#### Scenario: Slow provider
- **WHEN** the health result for search is `degraded` at 1,840 ms, checked 3 minutes ago
- **THEN** the Search card shows the warn icon, "Slow · checked 3m ago", and "1,840 ms, limit 1,000 ms" on the warn tint

#### Scenario: Down provider
- **WHEN** the health result for fetch is `down` with detail `ECONNREFUSED`
- **THEN** the Fetch card shows "Down · checked <ago>" on the danger tint and `ECONNREFUSED` in the mono font

#### Scenario: Check one card
- **WHEN** the user presses "Check" on the Scorer card
- **THEN** a health check for `score` only is posted, only the Scorer card shows "Checking…" until the result arrives, and the other cards keep their strips

#### Scenario: Check all
- **WHEN** the user presses "Check all providers"
- **THEN** one health check for every block is posted and every card shows "Checking…" until the new results arrive

#### Scenario: Server block names
- **WHEN** the health report lists the blocks `search`, `fetch`, `prefilter` (provider `embeddings`), `score`, and `llm`
- **THEN** the cards are titled Search, Fetch, Embeddings, Scorer, and LLM, and no card shows `prefilter` or `score` as its title

#### Scenario: Keyword prefilter
- **WHEN** the `prefilter` block's provider is `bm25`
- **THEN** its card is titled "Prefilter" and shows `bm25` as the provider name, never "Embeddings"

#### Scenario: Profile line with description
- **WHEN** the report's profile is `low-vram` and `GET /api/profiles` describes it as "Models take turns on one small GPU; slower, fits 8 GB."
- **THEN** the line reads "Active profile low-vram · Models take turns on one small GPU; slower, fits 8 GB." as in the prototype's Settings screen

#### Scenario: Exclusive policy
- **WHEN** the health report has `gpu_policy` `exclusive` and the prefilter, score, and llm providers all use device `desktop:gpu0`
- **THEN** Exclusive is selected, neither option can be changed, and the text reads "Each model unloads before the next one loads on desktop:gpu0."

#### Scenario: Device and Unload rows
- **WHEN** the score provider has device `desktop:gpu0` and release `llama-swap`
- **THEN** the Scorer card lists Device `desktop:gpu0` and Unload `llama-swap`

### Requirement: Writing defaults
The Settings screen SHALL show the "Writing defaults" panel with the
prototype's fields, in this order: Tone (a select whose options read
"<Tone> — <description>" for the 11 tones Objective "neutral and
evidence-first", Formal "precise, impersonal register", Analytical "breaks
the question into causes and factors", Persuasive "argues for a
recommendation", Informative "a plain, broad overview", Explanatory
"teaches how and why, step by step", Descriptive "a detailed account of
what exists", Critical "weighs strengths, weaknesses and gaps",
Comparative "sets the options side by side", Speculative "explores likely
futures and open questions", Reflective "considers implications and
trade-offs"; a saved tone not in the list is offered as itself), Custom
instructions (a textarea with the placeholder "e.g. Focus on costs; avoid
jargon."), Length (words) (100 to 4000, step 50, "words, approximately"),
Language (a select), Citation marker (segmented: "[1] Numeric",
"¹ Superscript", "(Author, year)"), and Reference style (segmented: APA,
MLA, Chicago, IEEE). Selects SHALL be `min(380px, 100%)` wide. Values SHALL
be loaded from `GET /api/settings`. Each change SHALL be saved with
`PUT /api/settings` without a save button, and a "Saved" mark with a check
SHALL show for 1.5 seconds after the server accepts it. When the server
rejects a value, the field SHALL show the server's error and the previous
value SHALL be restored. The same fields, labels, and controls SHALL be
used by the New run Options panel and the Rewrite dialog.

#### Scenario: Autosave
- **WHEN** the user changes Length (words) to 800
- **THEN** `PUT /api/settings` is sent with `words` 800 and "Saved" appears

#### Scenario: Rejected value
- **WHEN** the server rejects a change
- **THEN** the field shows the error and the earlier value is shown again

#### Scenario: Tone select
- **WHEN** the Settings screen shows the default tone `objective`
- **THEN** the Tone select shows "Objective — neutral and evidence-first" and lists the 11 tones with their descriptions

#### Scenario: Reference style as segments
- **WHEN** the user picks MLA in Reference style
- **THEN** `PUT /api/settings` is sent with `reference_style` "MLA"

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

### Requirement: Inline help
The UI SHALL offer the prototype's inline help (scenario `help`, figures A
to D): a help button placed 4 to 5px after a label or column header, 16px
round, transparent, with the Phosphor `question` icon at 15px in the
`--faint` color, `cursor: help`, an invisible hit area 6px larger on every
side (28px), and the accessible label "Help: <title>". Hovering it SHALL
show the text color on an 8% text-color tint; keyboard focus SHALL show
the Nocturne focus ring; while its tooltip is pinned open it SHALL show
the accent-300 color on a 22% accent tint.

The tooltip SHALL be one element with `role="tooltip"` referenced by the
button's `aria-describedby`, fixed-positioned above every other overlay
except the sign-in screen, 272px wide (at most the viewport width minus
16px), with padding 9px 12px 10px, the medium radius, the surface
background, the large shadow, 13px text at line height 1.45 in normal
weight, case, and letter spacing whatever its container uses, showing the
title (weight 600), the body, and, when the entry has one, "Example: "
(12px, muted) followed by the example in the mono font at 11.5px.

Placement: horizontally centred on the button and clamped to stay 8px
inside the viewport; below the button (9px gap) when more than 180px
remain below it or less than 180px remain above it, otherwise above it
(9px gap). A 10px square arrow rotated 45° SHALL point at the button's
centre (clamped to 10px from either end), on the top edge with a 1px
`--wa-ring` border on its top and left sides when below, and on the bottom
edge with the border on its bottom and right sides when above.

Behavior: at most one tooltip SHALL be open. Pointer hover or keyboard
focus SHALL open it; leaving or blurring SHALL close it after 140 ms
unless the pointer has entered the tooltip. A click or tap SHALL open it
pinned: a pinned tooltip ignores hover and blur, a second tap on the same
button closes it, and a tap on another help button pins that one instead.
A pointer press outside every help button and the tooltip, any scroll,
or Escape SHALL close it.

#### Scenario: Hover open (figure B)
- **WHEN** the user hovers the help button after "Recipe" on the New run screen
- **THEN** a tooltip titled "Recipe" opens 9px below the button with its arrow pointing at the button, and it closes 140 ms after the pointer leaves the button without entering the tooltip

#### Scenario: Keyboard focus
- **WHEN** the user tabs to a help button
- **THEN** the button shows the focus ring, the tooltip opens, and the button's `aria-describedby` names the tooltip

#### Scenario: Phone tap (figure C)
- **WHEN** on a 390px wide window the user taps the help button after "Profile"
- **THEN** the tooltip opens pinned and stays open until the user taps outside it, taps the same button again, scrolls, or presses Escape

#### Scenario: Near an edge, flipped (figure D)
- **WHEN** a help button sits 20px from the right edge and 30px from the bottom of the viewport and its tooltip opens
- **THEN** the tooltip opens above the button, its right edge is 8px inside the viewport, and the arrow on its bottom edge points at the button

#### Scenario: Example line
- **WHEN** the Attachments help opens
- **THEN** the tooltip shows "Attachments", "Markdown or text files to research alongside the web, or instead of it.", and "Example: pdf-ingest output (.md)"

#### Scenario: Only one open
- **WHEN** one help tooltip is pinned open and the user taps another help button
- **THEN** only the second tooltip is open

### Requirement: Shell help placements
The Settings and Run history screens SHALL place help buttons where the
prototype places them, with these titles and bodies verbatim (the
accessible label is "Help: <label>"):

| Placement | Label | Title | Body |
|---|---|---|---|
| Settings profile line, after the profile name | Profile | Profile | A named set of providers (search, fetch, embeddings, scorer, LLM) and GPU behavior. The list comes from the server. |
| After "GPU policy" | GPU policy | GPU policy | Shared keeps all models loaded. Exclusive unloads a model before the next one on the same GPU loads; it needs unload support. |
| Provider card, after "Device" | Device | Device | Where this provider runs, as labelled in the profile. |
| Provider card, after "Unload" | Unload | Unload | Whether the model can be released between phases: none, llama-swap or ollama. Exclusive GPU policy needs it. |
| Provider card health strip, after the health text | Health | Health | Not checked yet, OK, slow (degraded), down, or skipped (built in, no endpoint). Checks run only when you click Check, so idle GPU servers are never woken by opening this page. |
| After the "Writing defaults" heading | Writing defaults | Writing defaults | Used for every new run. Each run can override them in its options. |
| After "API tokens" in the Security panel | API tokens | API tokens | For scripts and agents on other machines. A token is shown once, when you create it. |
| History table header, after "Recipe" | Recipe | Recipe | Report wrote a cited report; context returned selected passages only. |
| History table header, after "Cost" | Cost | Cost | Total for search and hosted APIs across all stages. $0 for local models. |
| History rewrite note, after the writing changes | Rewrite marker | Rewrite | A new version written from an earlier run's passages. It opens next to its parent as linked versions. |

Every writing field label (Settings, New run, Rewrite dialog) SHALL be
followed by a help button with these entries:

| Label | Title | Body | Example |
|---|---|---|---|
| Tone | Tone | The writing style of the report. Each option in the list says what it emphasizes. | |
| Custom instructions | Custom instructions | Extra guidance added on top of the tone. Set a default here, or change it for one run. | Focus on costs; avoid jargon. |
| Length (words) | Length (words) | Target length of the report. The writer aims for it; it is not an exact count. | |
| Language | Language | The language the report is written in. Sources can be in any language. | |
| Citation marker | Citation marker | How citations look in the text. | [1] · ¹ · (Leviathan et al., 2023) |
| Reference style | Reference style | Format of the reference list at the end of the report: APA, MLA, Chicago or IEEE. | |

#### Scenario: Health help on a card
- **WHEN** the user hovers the help button in the Scorer card's health strip
- **THEN** the tooltip reads "Health" and "Not checked yet, OK, slow (degraded), down, or skipped (built in, no endpoint). Checks run only when you click Check, so idle GPU servers are never woken by opening this page."

#### Scenario: Help in an uppercase header
- **WHEN** the user opens the help after the History table's "Cost" header
- **THEN** the tooltip text is in normal case and weight, not the header's style

#### Scenario: Writing field help in Settings
- **WHEN** the user focuses the help button after "Citation marker" in Writing defaults
- **THEN** the tooltip shows "How citations look in the text." and "Example: [1] · ¹ · (Leviathan et al., 2023)"

### Requirement: Provider warning without probing
When the app starts after sign-in, it SHALL read `GET /api/providers/health`
once, without posting a health check, and SHALL set the Settings warn dot
when any entry has status `degraded` or `down`. Every later health report
the app receives (from Settings or from a check) SHALL update the dot the
same way. `unchecked` and `skipped` entries SHALL NOT set the dot. The app
SHALL NOT poll health in the background.

#### Scenario: Warn dot from a stored result
- **WHEN** the server's stored result has the llm block `down` and the user signs in on the New run screen
- **THEN** the Settings item shows the warn dot and no health check was posted

#### Scenario: Nothing checked
- **WHEN** every entry of the report is `unchecked` or `skipped`
- **THEN** the Settings item shows no warn dot

### Requirement: Run history depth tag
Each Run history row SHALL show the run's depth as an outline tag next to
its status tag ("Quick", "Standard", "Deep", "Exhaustive", or "Custom"), as
in the prototype's Run history screen, taken from the run's summary in
`GET /api/runs`. A run with no depth SHALL show "Standard".

#### Scenario: Depth in a row
- **WHEN** `GET /api/runs` returns a run with `depth = "exhaustive"`
- **THEN** its row shows the status tag followed by "Exhaustive"

#### Scenario: Older run
- **WHEN** a run's summary has `depth = null`
- **THEN** its row shows "Standard"

### Requirement: Run defaults
The Settings screen (scenario `settings`) SHALL show a "Run defaults"
section above "Writing defaults": the heading "Run defaults" followed by
its help button and the muted 12px text "Preselected on every new run ·
saved automatically", then the rows Allow domains and Block domains with
the chips input, hint, and help buttons of the New run domain rows (web-run
"Domain rows" and "Domain help"), without overridden marks. The rows SHALL
load from `GET /api/settings` (`domains`). Each change SHALL be saved with
`PUT /api/settings` without a save button, and the "Saved" mark with a
check SHALL show for 1.5 seconds after the server accepts it; a rejected
value SHALL show the server's error under the row and restore the previous
list. When any profile from `GET /api/profiles` sets its own list, the
section SHALL show the note "The <names> profiles set their own domain
lists; runs on those profiles use them instead.", with the profile names
joined by " and ". The section's help button SHALL read, verbatim: title
"Run defaults", body "Preselected on every new run. A profile can set its
own domain lists; runs on that profile use those instead." The prototype's
Format row in this section belongs to another change and SHALL NOT be shown
yet.

#### Scenario: Autosave a block list
- **WHEN** the user adds `pinterest.com` to Block domains in Settings
- **THEN** `PUT /api/settings` is sent with `domains.block` = `["pinterest.com"]` and "Saved" appears

#### Scenario: Profiles with their own lists
- **WHEN** `GET /api/profiles` returns `low-vram` with `block_domains = ["pinterest.com", "quora.com"]` and `nixos` with `block_domains = ["facebook.com"]`, and every other profile with null lists
- **THEN** the section shows "The low-vram and nixos profiles set their own domain lists; runs on those profiles use them instead."

#### Scenario: New run follows the default
- **WHEN** the selected profile sets no Allow list, the New run Allow row is not edited, and the user sets the global Allow default to `gob.pe`
- **THEN** the New run Allow row shows gob.pe without an "overridden" mark

# Spec Delta

## MODIFIED Requirements

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

### Requirement: Settings providers
The Settings screen of the prototype (no dedicated scenario; reached with
Alt+4 from any scenario) SHALL show the H1 "Settings" with a "Check all
providers" button, the active profile line, and a "Providers" grid with one
card per configured provider block from `GET /api/providers/health`, in the
order the server lists them, titled by block: `search` "Search", `fetch`
"Fetch", `prefilter` "Embeddings", `score` "Scorer", `llm` "LLM" (any other
block name capitalised), and showing the provider name, URL, and model.
Each card's health strip SHALL show the last result: `ok` as "Healthy · N
ms", `degraded` as "Slow · N ms" with the detail, `down` as "Unreachable ·
<detail>", and `skipped` as "Skipped · <detail>", with the matching
prototype icon and tint, and how long ago the result arrived. The server
checks all providers of the profile at once, so "Check" on a card and
"Check all providers" SHALL both run one health request; while it runs,
the cards SHALL show "Checking…" with the spinning dashed circle and the
Check buttons SHALL be disabled. The profile line SHALL name the checked
profile and the device labels its providers use. Secrets SHALL never be
shown.

#### Scenario: Slow provider
- **WHEN** the health result for search is `degraded` at 1,840 ms
- **THEN** the Search card shows the warn icon and "Slow · 1,840 ms" on the warn tint

#### Scenario: Check all
- **WHEN** the user presses "Check all providers"
- **THEN** every card shows "Checking…" until the new results arrive

#### Scenario: Server block names
- **WHEN** the health report lists the blocks `search`, `fetch`, `prefilter`, `score`, and `llm`
- **THEN** the cards are titled Search, Fetch, Embeddings, Scorer, and LLM, and no card shows `prefilter` or `score` as its title

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

## ADDED Requirements

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

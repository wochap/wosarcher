# Spec Delta

## MODIFIED Requirements

### Requirement: Live run header
The Live run screen (scenario `live`) SHALL show a header with the status
tag (Connecting, Running, Completed, Failed, Cancelled, with the
prototype's tints and pulses), a "rewrite of <id>" tag for a fork from the
write stage, the run id, the meta line `recipe · sources · profile [· N
files]`, and the query clamped to two lines. Actions: Cancel only while
the run status is queued or running, "Open report" when completed, Rerun
when failed, interrupted, or cancelled. Cancel SHALL send
`POST /api/runs/{id}/cancel` and SHALL be disabled until the request
answers. A 409 answer with `error = "run_not_active"` SHALL NOT show an
error: the app SHALL apply the `status` from the answer and refresh the run
(web-shell "Run status from the server"), so the header shows the ended
state and Cancel disappears. Rerun SHALL send `POST /api/runs/{id}/rerun`
(same request and attachments, a new run) and show the new run on the Live
run screen.

#### Scenario: Completed
- **WHEN** `run.done` is applied (end of scenario `live`)
- **THEN** the tag reads Completed, Cancel is gone, and "Open report" opens the Report screen

#### Scenario: Cancel a run that already failed
- **WHEN** the header still shows Running, the user presses Cancel, and the server answers 409 `run_not_active` with `status = "failed"`
- **THEN** no error toast is shown, the tag reads Failed (scenario `failure`), Cancel is gone, and Rerun is shown

#### Scenario: Cancel in flight
- **WHEN** the user presses Cancel and the server has not answered yet
- **THEN** the Cancel button is disabled

### Requirement: Reconnecting state
When the event connection drops during a run, the Live run screen SHALL
show the prototype scenario `reconnecting` as a banner, never a modal: warn
"Connection lost. Reconnecting (attempt N)… The run continues on the
server; events replay from seq <n>.", then, only once the new socket has
opened, "Reconnected. Replaying N missed events…", then "Reconnected ·
replayed N events, nothing lost." for 4.5 seconds. The screen SHALL stay
usable and the footer SHALL show the matching connection state.

#### Scenario: Recovery
- **WHEN** the connection drops at seq 351 and the second attempt succeeds and replays 54 events
- **THEN** the banner shows attempt 1, then attempt 2, then "Replaying 54 missed events", then "replayed 54 events, nothing lost", and disappears after 4.5 seconds

#### Scenario: Attempt that does not open
- **WHEN** a reconnect attempt's socket closes before opening
- **THEN** the banner goes from "Reconnecting (attempt N)" to "Reconnecting (attempt N+1)" and never shows "Replaying"

### Requirement: Rewrite
Rewrite on the Report screen (scenarios `finished` and `versions`) SHALL
open the prototype's "Rewrite report" dialog, prefilled with the viewed
version's writing options, marking each changed field "changed" with "was
<value>" and Reset, explaining that sources and passages are reused, and
showing "Creates v<N> linked to <id>", where N is the highest version in
the viewed run's lineage plus one, the version the server gives the fork.
"Rewrite from write stage" SHALL send `POST /api/runs/{id}/fork` with
`from` = `write` and the changed writing options, then show the new run on
the Live run screen (Report tab on phone) with reused phases, cached
sources, the passages of the run that scored them, and the banner "Rewrite
of <id>: sources and passages are reused, only the write stage runs."
until writing starts. Cancel, the close button, Escape, and a backdrop
click SHALL close the dialog without a request.

#### Scenario: Rewrite shorter
- **WHEN** the user sets the length to 250 and confirms
- **THEN** a fork from `write` with `words` 250 is created and shown live with Plan to Select marked reused

#### Scenario: Rewrite an older version
- **WHEN** the user views v1 of a lineage that has v1 and v2 and opens Rewrite
- **THEN** the dialog says "Creates v3", and the created run has version 3

## ADDED Requirements

### Requirement: Live updates unavailable state
When the event connection is "unavailable" (web-shell "Run event stream"),
the Live run screen SHALL show, in place of the reconnecting banner and
with the style of the prototype scenario `reconnecting` (warn tint,
`ph-wifi-slash` icon), the banner "Live updates unavailable. The server
did not accept the event connection; the run continues on the server and
its status is checked every 30 s." The footer connection state SHALL read
"Live updates unavailable" with a static warn dot. The header status, the
Cancel and Rerun actions, and the elapsed time SHALL follow the run status
from the server. When a later attempt opens, the screen SHALL return to
the `reconnecting` sequence ("Reconnected. Replaying N missed events…").

#### Scenario: Upgrade refused
- **WHEN** the socket for a running run closes without opening on the first connection and three attempts
- **THEN** the banner reads "Live updates unavailable…", it does not alternate with "Replaying", and the footer reads "Live updates unavailable"

#### Scenario: Run ends while unavailable
- **WHEN** the connection is unavailable and a status check returns `status = "done"`
- **THEN** the tag reads Completed, Cancel is gone, "Open report" is shown, and no further attempt is made

### Requirement: Run not found state
When the event socket closes with 4404 or `GET /api/runs/{id}` answers 404,
the Live run screen, and the Report screen for that run, SHALL show the
layout of the prototype scenario `empty` with the faint `ph-pulse` icon
replaced by `ph-question`, the title "Run not found", the text "Run <id>
does not exist on this server. It may have been deleted.", and the "New
run" button with the "Alt 1" hint. No other request for that run SHALL be
sent.

#### Scenario: Deleted run opened from a link
- **WHEN** the user opens `#/runs/<id>` for a run that was deleted
- **THEN** the Report screen shows "Run not found" with the run id, not a blank page

#### Scenario: Unknown run on Live run
- **WHEN** the user opens `#/live/<id>` and the socket closes with 4404
- **THEN** the Live run screen shows "Run not found" and the footer and banner are not shown

## MODIFIED Requirements

### Requirement: Sub-queries and sources panels
The Live run screen (scenario `live`) SHALL show the Sub-queries panel
(query ID, text, status queued, searching, "N results", reused, or
cancelled; summary `done/total`) and the Sources panel, newest first, each
row with icon, title linking to the URL in a new tab, URL without scheme,
and state: found, fetched, cached (for a fork), "failed", not
fetched (cancelled run), or for files the size; plus "N kept" once
passages are selected. A fetched page whose `page.fetched` has `thin` true
SHALL show the state "thin" in place of "fetched" or "cached", in the
muted tone. A failed page's state SHALL read "failed" in the danger color,
with the failure reason (when the event carries one) as its native tooltip
and in its accessible name ("failed: <reason>"); the reason SHALL NOT be
shown inline, and no row SHALL widen the panel past its width (scenario
`live`).

Each web source row SHALL show, under its URL, the IDs of every query
whose `hit.found` listed that URL, in query order (`q0` first), joined by
" · ", on its own line in the URL line's style. The same URL may arrive in
several `hit.found` events with overlapping query IDs (a later round, or
a merged hit); the row SHALL show the union, each ID once. Hovering
or focusing an ID SHALL show that query's text as a native tooltip, taken
from the Sub-queries or Research rounds data; an ID whose text is not known
yet shows no tooltip. File rows show no query IDs. The prototype has no
such line; it SHALL reuse the URL line's layout. The Sources summary SHALL read "N of M fetched · K
files" and a danger note "N failed · run continues" SHALL show while any
page failed.

Every Sub-queries row SHALL start with its query ID (`q0`, `q1`, …) in the
11px faint number column, matching the IDs of the Research rounds panel.
The first row is `q0`, the planner's topic line (scenario `live`): above
its text, on a line of its own, the row SHALL show the muted 11px label
"Topic line" followed by its help button (Requirement: Run help
placements), and it counts toward the
`done/total` summary like the other rows. Its status SHALL count the hits
of `q0`, whether they came from the search before planning or from the
Search phase.

#### Scenario: Topic row
- **WHEN** `plan.ready` lists `q0` "speculative decoding: draft-model size vs acceptance on 8–12 GB GPUs" and `q1` to `q3`
- **THEN** the Sub-queries panel shows four rows numbered `q0` to `q3`, the first showing the label "Topic line" and a help button above the topic text

#### Scenario: Failed page
- **WHEN** `page.failed` arrives with reason "403 Forbidden"
- **THEN** that row shows "failed" in the danger color with the tooltip "403 Forbidden", and the header shows "1 failed · run continues"

#### Scenario: Source found by two queries
- **WHEN** `hit.found` events list `https://www.gob.pe/371-inscribir-alerta-registral` for `q4` in round 1 and for `q7` in round 2
- **THEN** its Sources row shows "q4 · q7" under the URL, and hovering `q7` shows q7's text

#### Scenario: Thin page row
- **WHEN** `page.fetched` arrives for a URL with `thin` true
- **THEN** its Sources row shows the state "thin" and the summary counts it as fetched

#### Scenario: Search language kept in the draft
- **WHEN** the user types "es" as the search language, opens Settings, and returns to New run
- **THEN** the search language still reads "es"; after the user starts that run, New run shows it empty

#### Scenario: Long failure reason
- **WHEN** `page.failed` arrives with reason "firecrawl: cannot fetch https://pe.todosnegocios.com/c/..." (a 200-character reason)
- **THEN** the row's state reads "failed", the full reason shows on hover, and the Sources panel has no horizontal scrollbar

### Requirement: Recent and pinned runs
New run SHALL show a "Recent & pinned" list (scenarios `new-recent`,
`new-recent-empty`), built from `GET /api/runs`:
- **Pinned**: the pinned runs that still exist, in the order they were
  pinned.
- **Recent**: the 20 newest runs that are not pinned and have no
  `parent_run_id` (forks and rewrites are left out). Runs whose question,
  `form`, and attachment names are equal collapse into the newest one,
  marked "×<n>" with the title "<n> runs with this question and options;
  showing the newest".

A group with no row is not shown; with no row at all, the list shows the
clock icon, "No runs yet", and "Runs you start show up here. Pin the ones
you repeat to keep them on top." Each row SHALL be a button (32px tall on
desktop, 44px on phone) labelled "Fill the form from: <name>" with the
full question as its title, showing the name (the user's name for it,
else the question, cut with "…"), a summary "<Depth> · <recipe> ·
<sources> · <profile or custom (profile)> · <N> words" (for a catalog
run: "Catalog · <sources> · <profile or custom (profile)> · <N> nodes",
or "Catalog · <sources> · <profile or custom (profile)>" while its node
count is null), the paperclip
icon and "<n> file(s)" when it has attachments, the relative creation
date, and the "×<n>" mark. A row's "…" menu button ("Actions for
<name>") SHALL open a menu with Rename (pencil), Pin or Unpin (push-pin,
push-pin-slash), and Open run (arrow-square-out, opens the run as History
does). Rename turns the name into an input (at most 120 characters,
placeholder the question): Enter or leaving it saves, Escape cancels, and
an empty name or the question removes the custom name. Names and pins
SHALL be kept in browser storage by run ID, and IDs of runs the server no
longer lists SHALL be dropped.

Pressing a row SHALL fill the form and SHALL NOT start a run: the question;
Recipe, Sources, Depth (Custom with the run's research values, or
Standard when the preset no longer exists), and Length; the writing
overrides; the profile (the active profile when it no longer exists) and
its Advanced edits (`use` and `llm`); the domain lists and search
language; and the run's attachments as reused files (Requirement:
Attachments). Values come from the run summary's `form`; a field the
`form` leaves unset (sent as `null`) SHALL keep its default (the writing
defaults, or Standard's value for a Custom research value) and SHALL NOT
be filled as empty. A run without `form` fills the question, Sources,
Recipe, profile, and Depth from its summary. A summary's `writing` MAY be
`null` (a catalog run whose output is `table`); the list SHALL render and
fill without error, treating it as unset writing. Pressing a catalog run's
row SHALL fill only the question, Sources, and profile. When the form had a question or edits before, the toast "Filled
from “<name>”" (name cut at 28 characters) SHALL offer Undo, which
restores the previous form. The pressed row SHALL be marked (accent ring,
`aria-current`) while the form still matches it.

On windows at least 1200px wide (not phone) the list SHALL be a column
beside the form (the form at most 800px, the list 260 to 320px), sticky,
with the heading "Recent & pinned", its help button (`recent`), and the
row count. Otherwise it SHALL be a disclosure under the question,
collapsed by default: a caret, "Recent & pinned", "· <count>", and the
help button. The help text SHALL be verbatim from the prototype's `recent`
entry.

#### Scenario: Fill from a recent run
- **WHEN** the user presses the row of a run with depth Custom, recipe `report`, sources `both`, profile `low-vram`, Length 1500, and the attachments `notes/rag-chunking.md` and `notes/api-docs-sample.md` (scenario `new-recent`)
- **THEN** the form shows that question, Custom with the run's six values, `report`, `both`, `low-vram`, 1500 words, and both files marked "reused from" the row's name, and no run is started

#### Scenario: Fill from a run with unset fields
- **WHEN** the user presses the row of a Custom run whose `form` sets only the tone `critical` and `sub_queries` 6, with every other writing and research field `null` (scenario `new-recent`), and then opens Options
- **THEN** the form shows tone Critical, the language and other writing fields at their defaults, Custom with `sub_queries` 6 and Standard's other values, and the page shows no error

#### Scenario: Undo a fill
- **WHEN** the question box holds a typed question and the user presses a row
- **THEN** the toast "Filled from “<name>”" appears, and Undo brings back the typed question and the previous options

#### Scenario: Collapsed duplicates
- **WHEN** two runs asked the same question with the same form and attachment names
- **THEN** Recent shows one row for the newer run, marked "×2"

#### Scenario: Pin and rename
- **WHEN** the user pins a row and renames it "Weekly LLM digest"
- **THEN** the row moves to Pinned, shows "Weekly LLM digest", and keeps both after a reload of the page

#### Scenario: Forks left out
- **WHEN** a run was rewritten into a version 2
- **THEN** the version 2 run has no row of its own

#### Scenario: No runs
- **WHEN** `GET /api/runs` returns no run (scenario `new-recent-empty`)
- **THEN** the list shows "No runs yet" and the hint text

#### Scenario: Narrow window
- **WHEN** New run is shown 1000px wide
- **THEN** the list is a collapsed "Recent & pinned · <count>" disclosure under the question

#### Scenario: Catalog run in the list
- **WHEN** `GET /api/runs` lists a catalog run with `writing` null, sources `web`, profile `default`, and `nodes` 42, and the page is reloaded on New run (scenario `new-recent`)
- **THEN** its row shows "Catalog · web · default · 42 nodes", the page shows no error, and pressing the row fills the question, `web`, and `default` without starting a run

### Requirement: Question card
While a followed run is `waiting`, the Live run screen SHALL show the
prototype's question card (scenarios `live-clarify`, `live-clarify-idle`,
`live-round-input`) above the column grid on desktop and in place of the
Progress tab's content on phone: the title ("Before searching" for a
clarify pause, "After round <k>" or "After wave <k>" for a round pause),
the stepper "<i> / <N>" with one dot per question, the timeout chip
(Requirement: Presence and timeout), a 3px progress line (Requirement:
Presence and timeout), the context
line when present, the current question, its options as radio buttons
(`confirm`, `single`) or checkboxes (`multi`) with descriptions and the
"recommended" tag, the recommended options preselected, the "Other" row
with its input when allowed (typing selects it), keyboard hints 1 to 9,
and the footer Back, "Use recommended for the rest", and Next (reading
"Continue" on the last question). Enter SHALL be Next or Continue; 1 to 9
SHALL pick an option. The card SHALL hold answers per question so Back
keeps them. Continue SHALL post `POST /api/runs/{id}/continue` with every
question's answer; "Use recommended for the rest" SHALL fill the
remaining questions with their recommendations and post. The card SHALL
be built from `input.needed` and SHALL close on `input.answered`, also
when another client answered. A rejected post SHALL show the server's
detail under the footer and keep the card.

#### Scenario: Step through
- **WHEN** a clarify pause has four questions and the user picks "No" on question 1 and presses Next
- **THEN** the card shows question 2 of 4 with the second dot current and question 1's answer kept for Back

#### Scenario: Other selected by typing
- **WHEN** the user types in the Other input of a `multi` question
- **THEN** the Other row is checked and its text is sent as `other`

#### Scenario: Answered elsewhere
- **WHEN** `input.answered` arrives while the card is on question 3
- **THEN** the card closes and the timeline shows the answers note

### Requirement: Presence and timeout
While the question card is shown, the client SHALL send the presence
message (event-streaming "Presence message") at most every 10 seconds
while the user is active (pointer, key, or focus activity in the last 10
seconds and the tab visible). The timeout chip SHALL read "waiting for
you" with a pause icon while active, and, once idle, a timer icon with a
countdown from the run's `timeout` in `m:ss`, with the help entry
`qtimeout`. The 3px progress line SHALL be full (accent fill on the
line-colored track) while active and, once idle, shrink with the
countdown to empty at 0:00. Activity SHALL reset the countdown and the
line to full and send presence. A `timeout` of 0 SHALL show no chip and
no line. The same card and line SHALL serve research and catalog runs
(scenarios `live-clarify`, `live-clarify-idle`).

#### Scenario: Idle countdown
- **WHEN** the user stops interacting for 10 seconds with `timeout` 60
- **THEN** the chip shows the countdown from 1:00, the line starts shrinking from full (scenario `live-clarify-idle`), and no presence is sent

#### Scenario: Back from idle
- **WHEN** the countdown reads 0:47 and the user moves the pointer
- **THEN** the chip reads "waiting for you", the line is full again, presence is sent, and the next countdown starts from 1:00

#### Scenario: Line while active
- **WHEN** a catalog run's clarify card opens with `timeout` 60 and the user keeps moving the pointer
- **THEN** the 3px line shows full and the chip reads "waiting for you"

#### Scenario: No timeout
- **WHEN** the pause has `timeout` 0
- **THEN** the card shows neither the chip nor the line

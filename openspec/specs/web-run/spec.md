# web-run Specification

## Purpose

The browser screens for one research run: starting it, following it live
through every state, reading and exporting its cited report, and creating
and browsing its versions, matching the run scenarios of the design
prototype.

## Requirements

### Requirement: New run form
The New run screen SHALL match the prototype scenario `new`: the H1 "New
research run", the intro "wosarcher searches the web and your files, scores
passages for relevance, and writes a cited report.", the Question textarea
(focused when the screen opens), the hint "Ctrl + Enter to run", and the
"Run research" button, disabled while the question is blank. Ctrl+Enter or
Cmd+Enter in the question SHALL submit. The screen SHALL also show the
Recent & pinned list (Requirement: Recent and pinned runs). While the form
still equals what a row filled in, a neutral tag with the arrow-u-up-left
icon and "from: <row name>" SHALL follow the Question label, titled "The
form matches this run. Edit anything to clear."; any edit SHALL remove it
(scenario `new-recent`).

#### Scenario: Blank question
- **WHEN** the question contains only spaces
- **THEN** "Run research" is disabled and Ctrl+Enter does nothing

#### Scenario: Submit with the keyboard
- **WHEN** the user types a question and presses Ctrl+Enter
- **THEN** the run is started as if "Run research" was pressed

#### Scenario: From chip clears on edit
- **WHEN** the form was filled from the row "RAG chunking" and the user changes Sources
- **THEN** the "from: RAG chunking" tag is no longer shown

### Requirement: Attachments
The New run screen (scenario `new`) SHALL offer the prototype's drop zone:
click, Enter, or Space opens the file picker; dragging files over it
highlights it; dropping or picking adds the files. Only `.md` and `.txt`
files SHALL be added; others SHALL be skipped with the alert "Skipped
<names> — only .md and .txt are supported." A file with the name of an
already added file SHALL be ignored. Added files SHALL be listed with name,
size (`B` or `KB` with one decimal), and a remove button. A file taken
from an earlier run (Requirement: Recent and pinned runs) SHALL show,
after its name, the recycle icon and "reused from <run name>" (scenario
`new-recent`), and SHALL be sent as `reuse_attachments` instead of being
uploaded; removing it works like removing any file.

#### Scenario: Mixed drop
- **WHEN** the user drops `notes.md` and `paper.pdf`
- **THEN** `notes.md` is listed and the alert says `paper.pdf` was skipped

#### Scenario: Remove
- **WHEN** the user presses the remove button of `notes.md`
- **THEN** `notes.md` is no longer listed

#### Scenario: Reused attachment sent by name
- **WHEN** the form was filled from run `r1` with `notes.md`, the user adds `extra.md`, and starts the run
- **THEN** the request uploads only `extra.md` and has `reuse_attachments` = `{"run_id": "r1", "names": ["notes.md"]}`

### Requirement: Run options
The New run screen (scenario `new`) SHALL show the collapsible "Options"
panel, collapsed by default. Its header SHALL show the summary "<Depth> ·
<recipe> · <sources> · <profile> · <N> words · <Tone>", as in scenario
`new-depth`, where <profile> reads "custom (<profile>)" when the profile's
Advanced values have edits (Requirement: Profile advanced values). The
panel SHALL start with the Depth group (Requirement: Depth control), then
the Run group. The Run group SHALL offer:
- Recipe (segmented, `report`, `answer`, then `context`);
- Sources (segmented, `web`, `files`, `both`);
- Profile: with six or fewer profiles from `GET /api/profiles`, a
  segmented control with one segment per profile by name, as Depth's
  (scenario `new-profile-custom`); with more (prototype setting
  `profiles = many`), a select `min(260px, 100%)` wide listing them. The
  active profile is preselected. While the profile's Advanced values have
  edits, the segmented control SHALL add a selected `custom` segment last
  (no profile segment is selected), or the select a selected option
  "custom (<profile>)", and the line "based on **<profile>** · <N>
  edit(s)" SHALL show under the control. Picking a named profile while
  edits exist SHALL drop them (Requirement: Profile advanced values) and
  show the toast "Dropped <N> edit(s) to <profile>" with Undo, which
  restores the profile and its edits. The selected profile's
  `description` is shown under the control (12px, muted, 4px above) when
  it is not empty, followed by the profile's Advanced toggle;
- Allow domains and Block domains (Requirement: Domain rows);
- Search language: a text input `min(260px, 100%)` wide with the
  placeholder "Any language" and a help button reading "Search language" /
  "Language SearXNG searches in. Use all, auto, or a language code: two or
  three lowercase letters, optionally followed by a script or region, such
  as es, es-PE, or zh-Hans-CN. Leave empty to search every language."
  Under the input, a faint hint SHALL read "all, auto, es, es-PE…" while
  the input is empty or valid. The value SHALL be kept with the other
  options of the New run draft while the user moves between screens, and
  cleared with the draft after a run starts; a fresh draft starts empty. A
  trimmed non-empty value SHALL be sent as `search_language`; an empty one
  sends no `search_language`. A value that breaks the search language rule
  (http-api "Create a run") SHALL replace the hint with the danger note
  "Use all, auto, or a code such as es or es-PE." under the input and
  disable Start until fixed. The prototype has no such
  row; it SHALL reuse the Profile row's label, input, and note styles.

Each Run label sits at the top of its row in the prototype's form grid.
Recipe `context` SHALL start the run with `until` set to `select`, so no
report is written. Recipes `report` and `answer` SHALL start the run with
`writing.format` set to the recipe. The Recipe SHALL be preselected from
the global default `writing.format` (web-shell "Run defaults"); when that
default changes while the New run screen keeps the previous default as its
Recipe, the Recipe SHALL follow the new default, and a Recipe the user
picked otherwise SHALL stay. `format` is not a Writing group field and
SHALL NOT show an "overridden" mark or count toward the header's overridden
count.

#### Scenario: Answer recipe
- **WHEN** the user picks Recipe `answer` and starts a run
- **THEN** the run request has `writing.format` = `answer` and no `until`

#### Scenario: Recipe follows the default format
- **WHEN** the global default format is `answer` and the user opens New run (scenario `new`)
- **THEN** Recipe `answer` is selected

#### Scenario: Context recipe
- **WHEN** the user picks Recipe `context` and starts a run
- **THEN** the run request has `until` = `select`

#### Scenario: Profile description
- **WHEN** `GET /api/profiles` returns `low-vram` with the description "Models take turns on one small GPU; slower, fits 8 GB." and the user selects it (scenario `new-profile`)
- **THEN** the control shows `low-vram` selected and the description is shown under it

#### Scenario: Profiles as segments
- **WHEN** `GET /api/profiles` returns four profiles
- **THEN** the Profile row shows a segmented control with the four names and no select

#### Scenario: Many profiles
- **WHEN** `GET /api/profiles` returns seven profiles (prototype setting `profiles = many`)
- **THEN** the Profile row shows a select listing the seven names

#### Scenario: Custom segment
- **WHEN** the profile `cloud` has three Advanced edits (scenario `new-profile-custom`)
- **THEN** the segmented control ends with a selected `custom` segment, no profile segment is selected, and "based on cloud · 3 edits" shows under it

#### Scenario: Dropping edits can be undone
- **WHEN** `cloud` has three edits and the user picks the `low-vram` segment
- **THEN** `low-vram` is selected without edits, the toast reads "Dropped 3 edits to cloud", and Undo selects `cloud` with its three edits again

#### Scenario: Summary
- **WHEN** the depth is Deep, recipe `report`, sources `both`, profile `workstation` without edits, tone objective, and words 2000
- **THEN** the collapsed header reads "Deep · report · both · workstation · 2000 words · Objective"

#### Scenario: Summary with profile edits
- **WHEN** the same options are set and the Scorer was changed for this run
- **THEN** the collapsed header reads "Deep · report · both · custom (workstation) · 2000 words · Objective"

#### Scenario: Domain rows in the Run group
- **WHEN** the user opens the Options panel (scenario `new-domains`)
- **THEN** the Run group shows Recipe, Sources, Profile, Allow domains, Block domains, and Search language, in that order

#### Scenario: Search language left empty
- **WHEN** the user starts a run without typing a search language
- **THEN** the run request has no `search_language`

#### Scenario: Search language set
- **WHEN** the user types " es-PE " as the search language and starts a run
- **THEN** the run request has `search_language` = `es-PE`

#### Scenario: Invalid search language
- **WHEN** the user types "spanish" as the search language
- **THEN** the row shows "Use all, auto, or a code such as es or es-PE." in place of the hint, and Start is disabled

#### Scenario: User profile marked
- **WHEN** `GET /api/profiles` returns a profile `nixos`
- **THEN** its segment reads "nixos", with no "(user profile)" suffix since every profile is a user file, and selecting it sends `profile` = `nixos`

### Requirement: Writing overrides
The Writing group of the Options panel (scenario `new`) SHALL use the
writing fields, labels, and controls of the Settings "Writing defaults"
panel. It SHALL start from the saved writing defaults, except Length
(words): its default is the selected depth's `words`, or the saved default
when the depth sets none (Standard), or the last Custom value for Custom.

A field whose value differs from its default SHALL show the "overridden"
mark followed by its help button, "default: <value>", and a Reset button.
For Length (words) under a depth that sets the default, that text reads
"<Depth> default: <N> words" and the help button is "Depth default". While
Length is not overridden, its hint reads "set by <Depth>" (none for Custom).
A custom instruction longer than 28 characters SHALL read as its first 28
characters followed by "…" in that text.

The panel header SHALL show "N overridden". The group SHALL offer "Reset all
to defaults" while any field is overridden, and an "edit defaults" link to
Settings. When a default changes in Settings or through the depth, the New
run value of that field SHALL follow it unless it is overridden. The run
request SHALL carry only the overridden writing fields.

#### Scenario: One override
- **WHEN** the depth is Standard, the default length is 1200, and the user sets 600
- **THEN** Length (words) shows "overridden" and "default: 1200 words", the header shows "1 overridden", and the request sends `words` 600 and no other writing field

#### Scenario: Default follows Settings
- **WHEN** the tone is not overridden and the user changes the default tone in Settings
- **THEN** the New run tone shows the new default without an "overridden" mark

#### Scenario: Long custom instructions as default
- **WHEN** the default custom instructions are "Assume the reader knows CUDA well." and the user clears them for this run
- **THEN** the field shows "default: “Assume the reader knows CUDA…”"

#### Scenario: Length follows depth
- **WHEN** Length is not overridden and the user picks Deep
- **THEN** Length shows 2000 with the hint "set by Deep", and the request sends no `words`

#### Scenario: Edited length survives a depth change
- **WHEN** the user sets Length to 800 under Deep and then picks Quick
- **THEN** Length stays 800 and shows "Quick default: 600 words"

### Requirement: Start a run
Starting a run SHALL send `POST /api/runs` with the question, the run options,
the overridden writing fields, and the attachments, then show the new run
on the Live run screen and make it the followed run. When the server
rejects the request, the New run screen SHALL keep every input and show the
error box of the prototype scenarios `new-error` and `new-domain-error`,
8px below the Run research button, with `role="alert"`: the danger-tinted
box with the warning-circle icon, the title "Couldn’t start the run", and
the server's message below it in the mono font (11.5px, muted, wrapping
anywhere). When the error names a New run field (a domain list), the box
SHALL also show the ghost button "Fix in Options", which opens the Options
panel and focuses that field; otherwise the button SHALL NOT be shown.
Editing the named field SHALL clear the box. The box SHALL use the
Nocturne variables only.

#### Scenario: Started
- **WHEN** the server accepts the run and returns its id
- **THEN** the Live run screen shows that run with status Connecting

#### Scenario: Rejected without a field
- **WHEN** the server answers 422 with the detail "profile "gpu-box" does not exist. Known profiles: low-vram, workstation, cloud." (scenario `new-error`)
- **THEN** the question and options are kept, the box shows "Couldn’t start the run" and the message, and no "Fix in Options" button is shown

#### Scenario: Rejected domain entry
- **WHEN** the server rejects `domains.allow` because of the entry `gob.pe/tramites` (scenario `new-domain-error`)
- **THEN** the box shows the message and "Fix in Options"; pressing it opens the Options panel and focuses Allow domains

### Requirement: Live run header
The Live run screen (scenario `live`) SHALL show a header with the status
tag (Connecting, Queued, Running, Completed, Failed, Cancelled, with the
prototype's tints and pulses), a "rewrite of <id>" tag for a fork from the
write stage, the origin label for a run not started in the browser
(scenarios `live-cli` and `live-api`), the run id, the meta line
`recipe · sources · profile [· N files]`, and the query clamped to two
lines. The origin label SHALL be the prototype's small muted outlined
monospace label after the depth and rewrite tags: a terminal-window icon
and `cli` with the title "Started from the wosarcher CLI on this
machine" for origin `cli`, and a key icon and `api · <token name>` with
the title "Started through the API with token “<token name>”" for origin
`api`. A run with origin `web` SHALL show no origin label. When the query
is longer than 240 characters (scenario `long-brief`), a ghost text button
SHALL follow the query: a caret-down icon, "Show full question", and "·
<N> characters" in the faint color, where N is the query's character
count with thousands separators (for example "4,030 characters").
Pressing it SHALL show the whole query as plain text, line breaks kept and
Markdown marks (`#`, `**`, list markers) shown as typed, never rendered as
formatting, in a tinted box no taller than the smaller of 40% of the
viewport and 360px that scrolls inside itself, and SHALL change the button
to a caret-up icon and "Show less"; pressing again SHALL restore the
two-line clamp. The button SHALL carry `aria-expanded` and `aria-controls`
naming the query element. A query of 240 characters or fewer SHALL show
no button. Actions: Cancel only while the run status is queued or running,
"Open report" when completed, Rerun when failed, interrupted, or
cancelled. For a run with origin `web`, Cancel SHALL send
`POST /api/runs/{id}/cancel` at once. For a run with origin `cli` or `api`,
Cancel SHALL first open the prototype's confirm dialog (scenario
`cancel-cli`): the title "Cancel this CLI run?" or "Cancel this API run?";
the body "An agent started this run with the wosarcher CLI on this
machine. Cancelling stops it for the agent too: its command exits and
reports the run as cancelled." for `cli`, or "It was started through the
API with token “<token name>”. The caller gets the run back as cancelled."
for `api`; the muted line "Completed stages are kept. Nothing is
written."; and the buttons "Keep running", which closes the dialog, and
"Cancel run" (danger outline, stop icon), which sends the cancel request.
Cancel SHALL be disabled until the request answers. A 409 answer with
`error = "run_not_active"` SHALL NOT show an error: the app SHALL apply
the `status` from the answer and refresh the run (web-shell "Run status
from the server"), so the header shows the ended state and Cancel
disappears. Rerun SHALL send `POST /api/runs/{id}/rerun` (same request and
attachments, a new run) and show the new run on the Live run screen.

#### Scenario: Completed
- **WHEN** `run.done` is applied (end of scenario `live`)
- **THEN** the tag reads Completed, Cancel is gone, and "Open report" opens the Report screen

#### Scenario: Cancel a run that already failed
- **WHEN** the header still shows Running, the user presses Cancel, and the server answers 409 `run_not_active` with `status = "failed"`
- **THEN** no error toast is shown, the tag reads Failed (scenario `failure`), Cancel is gone, and Rerun is shown

#### Scenario: Long question
- **WHEN** the run's query is a 4,030-character brief (scenario `long-brief`)
- **THEN** the header shows the query clamped to two lines and the button "Show full question · 4,030 characters"; pressing it shows the whole brief in a scrolling box and the button reads "Show less · 4,030 characters"

#### Scenario: Short question
- **WHEN** the run's query has 120 characters
- **THEN** no "Show full question" button is shown

#### Scenario: Cancel in flight
- **WHEN** the user presses Cancel and the server has not answered yet
- **THEN** the Cancel button is disabled

#### Scenario: CLI run header
- **WHEN** the Live run screen shows a running run with origin `cli` (scenario `live-cli`)
- **THEN** the header shows the `cli` origin label with the terminal-window icon after the depth tag

#### Scenario: API run header
- **WHEN** the Live run screen shows a running run with origin `api` and token `ci-runner` (scenario `live-api`)
- **THEN** the header shows the label `api · ci-runner` with the key icon

#### Scenario: Confirm before cancelling a CLI run
- **WHEN** the user presses Cancel on a running CLI run (scenario `cancel-cli`)
- **THEN** the "Cancel this CLI run?" dialog opens and no request is sent until "Cancel run" is pressed

#### Scenario: Keep running
- **WHEN** the confirm dialog is open and the user presses "Keep running"
- **THEN** the dialog closes and no cancel request is sent

#### Scenario: Web run cancels at once
- **WHEN** the user presses Cancel on a running run with origin `web`
- **THEN** the cancel request is sent with no dialog

### Requirement: Phase timeline
The Live run screen (scenario `live`) SHALL show the phases Load, Plan,
Search, Fetch, Chunk, Prefilter, Score, Select, and Write, in the order the
pipeline runs them, as the prototype's cards. A multi-round run (resolved
`research.rounds` > 1) SHALL also show a Gap card between Score and Select
(scenarios `rounds-live`, `rounds-done`). Each card has an icon, the full
label (never truncated) followed by the phase's help button, progress
text, a time row (Requirement: Time per stage), and a 3px progress bar.
Cards are styled per state:
- pending;
- waiting: warn dashed border, stripes, CPU icon, text "waiting for GPU ·
  <reason>";
- running: accent, spinning icon, glow;
- done;
- reused: "reused from <parent id>";
- failed: danger, with the error;
- cancelled.

Cards SHALL have no title tooltip on the card itself. On desktop each card
SHALL be at least 98px wide, and the row SHALL scroll sideways when the
cards do not fit. On phone the cards use two columns. Waiting SHALL never
look like running. Phases that a run's recipe skips SHALL show done with
"skipped"; Load skipped in a run with sources `web` SHALL read "web only".

In a multi-round run, loop cards (Search to Score) SHALL show "round
<k>/<N>" while running, "round <k> done" between rounds, and "<n> rounds"
when the loop is done. The Gap card SHALL show:
- "pending" before it first runs;
- "reading round <k>" while it runs;
- "<n> follow-ups" after a gap step that continued;
- "<ran> of <N> rounds" once research is done.

The Gap help text SHALL be verbatim from the prototype's `ph-gap` entry.

#### Scenario: Waiting for a device
- **WHEN** the score stage has `resource.waiting` with released stage `prefilter` and has not started
- **THEN** the Score card shows the waiting style and "waiting for GPU · prefilter unloading"

#### Scenario: Narrow desktop window
- **WHEN** the Live run screen is 900px wide
- **THEN** every phase label is shown in full and the phase row scrolls sideways

#### Scenario: Round 2 running
- **WHEN** a three-round run is in round 2's fetch (scenario `rounds-live`)
- **THEN** the Fetch card shows "round 2/3", and the Gap card shows the follow-up count of the gap step after round 1

#### Scenario: Single round
- **WHEN** a run has `research.rounds = 1`
- **THEN** no Gap card is shown

#### Scenario: Load first
- **WHEN** a run with sources `web` is shown (scenario `done-quick`)
- **THEN** Load is the first card and reads "web only"

### Requirement: Phase method tags
On the Live run screen (scenario `live`), the Plan, Prefilter, Score, and
Write phase cards SHALL show the prototype's method tag below the label
while the phase is running, done, reused, failed, or cancelled. The tag is
a mono 10.5px button with a 1px solid divider border. It reads the model
for `llm` and `embeddings` providers, `BM25` for `bm25`, and the provider
name otherwise (`jev`, `rerank`, `passthrough`, `none`). While running the
tag uses the configured provider. After `stage.done` it uses the provider
that ran. A fallback phase (web-shell "Run view state") SHALL read
"<tag> · fallback" with the warn icon, a dashed warn border, and warn text.
The tag SHALL size to its text and end with "…" only when the card is too
narrow for it. The tag SHALL open the inline help tooltip (web-shell
"Inline help") with accessible label "Method: <tag>, details":

- Plan and Write: title "Planner · <model>" or "Writer · <model>", body
  "The configured LLM" plus ", on <device>." when the block has a device,
  else ".".
- Prefilter, as configured: title "Prefilter · embeddings" or "Prefilter ·
  keyword (BM25)"; the body names the model when there is one, the top N
  per sub-query, the kept count "K of C", and the passthrough sub-queries
  when any.
- Prefilter, fallback: title "Fallback · keyword (BM25)"; the body names
  the configured method and model, the reason from the stage's warnings,
  and the same counts.
- Score: title "Scorer · <tag>"; the body says whether it ran as
  configured, and on a fallback names the configured scorer and the reason
  from the stage's warnings.

The Passages panel scorer tag (`<scorer> · fallback`) and the phase tags
SHALL decide fallback the same way.

#### Scenario: Embeddings ran as configured
- **WHEN** the prefilter stage started with `embeddings:bge-small-en-v1.5` and finished with the same provider
- **THEN** the Prefilter card shows the tag "bge-small-en-v1.5" with a solid border

#### Scenario: Prefilter fell back to BM25
- **WHEN** the prefilter stage started with `embeddings:bge-small-en-v1.5` and finished with `bm25` and the warning "embeddings prefilter failed, used bm25: connection refused"
- **THEN** the Prefilter card shows "BM25 · fallback" with a warn icon and a dashed warn border, and its tooltip names embeddings, bge-small-en-v1.5, and "connection refused"

#### Scenario: Pending phase has no tag
- **WHEN** the score stage has not started
- **THEN** the Score card shows no method tag

### Requirement: Prefilter card detail
The Prefilter phase card (scenario `live`) SHALL show a second muted 11px
line under its progress text, clipped with "…": "top N per sub-query"
while running, and "top N/sub-query" once done or reused, followed by " ·
<IDs> passthrough" when any sub-query skipped ranking (IDs joined by ", ").
N SHALL come from the run's `score.candidates` in its request settings. A
pending, waiting, or skipped Prefilter card SHALL have no detail line.

#### Scenario: Done with passthrough sub-queries
- **WHEN** the prefilter stage is done with `score.candidates = 50` and passthrough `q4`, `q5`
- **THEN** the card's detail line reads "top 50/sub-query · q4, q5 passthrough"

#### Scenario: Running
- **WHEN** the prefilter stage is running with `score.candidates = 50`
- **THEN** the card's detail line reads "top 50 per sub-query"

### Requirement: Device chip
On desktop, while the run is queued or running and any stage has a device
label, the Live run header (scenario `live`) SHALL show the prototype's
device chip: the CPU icon, the label in the mono font at 11.5px, and the
device help button, with no title tooltip and no memory figures. The label
SHALL be "<device>" of the stage that runs (accent icon); "<device> ·
waiting" when no stage with a device runs and one waits for its device
(warn icon); otherwise the device of the most recently started stage that
had one (faint icon).

#### Scenario: Scorer running
- **WHEN** the score stage runs on device `desktop:gpu0`
- **THEN** the chip reads "desktop:gpu0" and shows no memory figure and no stage name

#### Scenario: Waiting for the device
- **WHEN** the score stage waits for `desktop:gpu0` and no stage with a device runs
- **THEN** the chip reads "desktop:gpu0 · waiting" with the warn icon

### Requirement: Sub-queries and sources panels
The Live run screen (scenario `live`) SHALL show the Sub-queries panel
(query ID, text, status queued, searching, "N results", reused, or
cancelled; summary `done/total`) and the Sources panel, newest first, each
row with icon, title linking to the URL in a new tab, URL without scheme,
and state: found, fetched, cached (for a fork), the failure reason, not
fetched (cancelled run), or for files the size; plus "N kept" once
passages are selected. A fetched page whose `page.fetched` has `thin` true
SHALL show the state "thin" in place of "fetched" or "cached", in the
muted tone.

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
- **THEN** that row shows "403 Forbidden" in the danger color and the header shows "1 failed · run continues"

#### Scenario: Source found by two queries
- **WHEN** `hit.found` events list `https://www.gob.pe/371-inscribir-alerta-registral` for `q4` in round 1 and for `q7` in round 2
- **THEN** its Sources row shows "q4 · q7" under the URL, and hovering `q7` shows q7's text

#### Scenario: Thin page row
- **WHEN** `page.fetched` arrives for a URL with `thin` true
- **THEN** its Sources row shows the state "thin" and the summary counts it as fetched

#### Scenario: Search language kept in the draft
- **WHEN** the user types "es" as the search language, opens Settings, and returns to New run
- **THEN** the search language still reads "es"; after the user starts that run, New run shows it empty

### Requirement: Passages panel
The Live run screen SHALL show the Passages panel as the prototype does in
scenarios `live` and `passages` (`design/project/wosarcher.dc.html`).

Header, first row: "Passages"; a neutral mono tag with the scorer that
produced the scores (the first query's scorer other than `passthrough`,
else `passthrough`), reading "<scorer> · fallback" when it is not the
run's configured `score.provider`, followed by the scorer help button; and,
at the right, a segmented control labelled "Show passages (R cycles)" with
the options Cited, Kept, and All, each followed by its count in the faint
color, then an "R" key hint. The default option SHALL be Kept. The R key
outside text fields SHALL select the next option (Cited, Kept, All, then
Cited again).

Header, second row: a funnel of four steps separated by caret icons:
chunks (the chunk stage count), scored (pairs scored, summed over
queries), kept (pairs kept, summed over queries), and cited (selected
passages). Each step SHALL show its number and label, or "–" in the faint
color until its stage reports it, and SHALL be a text button that opens
its help tooltip (web-shell "Inline help" tooltip) with the accessible
label "<number or pending> <label>, help". At the right of the row, the
label "Fates" SHALL be followed by a help button that opens the fate
legend. The header SHALL never overlap its controls; it wraps when narrow.

Counts: Cited is the number of selected passages, shown once select is
done; Kept is the kept count, shown once score is done; All is the scored
count, shown once any query is scored.

Cards, best display score first: the display score (two decimals), a 0 to
1 bar with a 1px marker at the display threshold of that passage's query
(title "threshold <value>"), the domain or file path, the heading path
joined by " › ", the text clamped to three lines, and one fate badge. Each
badge SHALL show its own icon, label, and border style, so fates differ
without color:

| Fate | When | Label | Card |
|---|---|---|---|
| cited | selected | "cited" and the citation label in the run's marker style | full |
| kept · selecting | kept, select not done | "kept · selecting" | full |
| ≥ threshold | kept, score not done | "≥ <threshold>" | full |
| source cap | skipped by select, reason `source_cap` | "source cap" | dimmed |
| over budget | skipped by select, reason `budget` | "over budget" | dimmed |
| query cap | not kept, drop reason `query_cap` | "query cap" and the query tag (for example "q1") | dimmed |
| below threshold | not kept, drop reason `threshold` | "below <threshold of its query>" | dimmed |

The Cited option SHALL list cited passages; Kept SHALL list every kept
passage (cited, kept · selecting, ≥ threshold, source cap, over budget);
All SHALL add the passages that were not kept. A chunk SHALL appear once:
when it is kept for any query, as that kept pair; otherwise as its pair
with the highest display score. Passages not kept come from the run's
`scores.jsonl` and `chunks.jsonl`, and select skips from `select.jsonl`,
loaded when first needed, with display scores mapped as the server maps
them. Passages from the `passthrough` scorer have no score: they SHALL show
"–" and no bar.

In the All view, passages below the threshold SHALL be collapsed into one
line after the list, "<N> more below <threshold> not listed (<lowest>–
<highest>)", with a "Show" button that lists them in score order and then
reads "Hide". The threshold is the shared display threshold when every
scored query has the same one, and "the threshold" otherwise.

Empty states SHALL use the prototype's texts: waiting for the run, scorer
waiting for the GPU, cancelled before scoring, the Cited option before
select is done ("Citations are assigned when Select finishes. Switch to All
to watch scores arrive."), the Kept option before score is done ("Kept
passages are known once scoring finishes. Switch to All to watch scores
arrive."), and passages not yet scored ("Passages appear as they are
scored. The prefilter narrows <chunks> chunks to <candidates> for the
scorer.").

#### Scenario: Default filter
- **WHEN** a finished run opens on the Live run screen
- **THEN** the Kept option is selected and the list holds every kept passage with its fate badge

#### Scenario: R cycles the filter
- **WHEN** the Kept option is selected and the user presses R outside a text field
- **THEN** All is selected; pressing R twice more selects Cited, then Kept

#### Scenario: Query cap is not a threshold rejection
- **WHEN** a passage with display 0.65 was dropped by the query cap of `q1` and a passage with display 0.64 is cited as [14]
- **THEN** the first card shows "query cap" with the tag "q1" and is dimmed, and the second shows "cited" with "[14]"

#### Scenario: Select skips
- **WHEN** select is done and a kept passage was skipped with the reason `source_cap`
- **THEN** its card shows "source cap" and is dimmed

#### Scenario: Kept before select
- **WHEN** score is done and select is still running
- **THEN** kept passages show "kept · selecting" and the funnel shows "–" for cited

#### Scenario: Funnel numbers
- **WHEN** a run chunked 612 chunks, scored 150 pairs, kept 30, and cited 25
- **THEN** the funnel reads "612 chunks › 150 scored › 30 kept › 25 cited"

#### Scenario: Collapsed tail
- **WHEN** the All option is selected and 121 scored passages are below a shared threshold of 0.50, scoring between 0.02 and 0.13
- **THEN** the list ends with "121 more below 0.50 not listed (0.02–0.13)" and a Show button, and pressing Show lists those passages dimmed with "below 0.50"

#### Scenario: Toggle rejected
- **WHEN** scoring is done and the user selects All
- **THEN** passages that were not kept appear dimmed with their fate badges, in score order with the kept ones

#### Scenario: Scorer tag and threshold in the summary
- **WHEN** the run's configured scorer is `jev`, every query was scored by `jev` with display threshold 0.6, and the score stage kept 14 of 96
- **THEN** the header shows the tag "jev", the funnel shows "96 scored › 14 kept", and the kept step's help reads "Scored at least 0.60 (threshold) …"

#### Scenario: Threshold from the scorer
- **WHEN** the scorer's display threshold for a query is 0.5
- **THEN** the marker of that query's passages sits at 50% of the bar

#### Scenario: Fallback scorer
- **WHEN** the configured scorer is `rerank` and the passages were scored by `bm25`
- **THEN** the tag reads "bm25 · fallback"

### Requirement: Passages header layout
The Passages panel header (scenario `live`) SHALL never draw its parts over
each other at any panel width. The summary SHALL shorten with "…" before it
reaches the Rejected toggle, and its help button SHALL stay visible. The
Rejected toggle's clickable area SHALL fit its switch, label, and key hint
with no more than 4px of padding on each side.

#### Scenario: Narrow panel
- **WHEN** the Passages panel is 440px wide and the summary reads "30 kept of 150 scored · ≥ 0.50"
- **THEN** the summary, its help button, and the Rejected toggle do not overlap

### Requirement: Source dialog
Clicking a passage card in the Passages panel, or pressing Enter or Space on
a focused card, SHALL open the Source dialog for that card's source with
that chunk selected. It SHALL match prototype scenario `source`. The dialog
SHALL load the source view of http-api "Source view".

Header:
- The source's title.
- For a web source: the domain, and an "Open original" link that opens
  the URL in a new tab.
- For a file source: the file name and "Attached file · no URL" (scenario
  `source-file`).
- The line "<N> chunks · <S> scored · <C> cited".
- A close button.

Fate block, for the selected chunk:
- its fate badge (the badge of the Passages panel for the same fate) and
  its score (two decimals);
- its heading path;
- a "why" line in the prototype's wording:
  - prefiltered: "Not scored: outside the top <k> for every sub-query.";
  - pending: "Waiting for the scorer.";
  - below threshold: "Scored <s> in <q>, below the <t> threshold.";
  - query cap: "Scored <s> in <q> but ranked <r> of <n> above <t>; <q>
    keeps only its top <cap>.";
  - kept: "Kept: rank <r> of <k> in <q>. Selection is running.";
  - cited: "Kept: rank <r> of <k> in <q>; cited as <label>.", with the
    label in the run's citation marker style;
  - source cap: "Kept: rank <r> of <k> in <q>; not cited: this source
    already has <m> cited passages (cap <m> per source).";
  - over budget: "Kept: rank <r> of <k> in <q>; not cited: needs <x>
    tokens, <y> were left in the budget.".
- A per-sub-query row: one chip per sub-query, holding its ID, its score
  when scored, and its state ("kept", "query cap", "below <t>", "counted
  in <q>", "prefiltered", "not in results", "pending"). The primary
  sub-query's chip is outlined in the accent color. The title attribute
  is the sub-query text.

Body:
- Every chunk of the source, in page order. A section heading shows
  where the top-level heading changes, and the sub-heading path is muted.
- Each chunk shows its fate badge and its score when scored.
- The selected chunk has the accent tint and ring and full opacity, and
  is scrolled into view. Other chunks are at half opacity.
- Clicking a chunk, or pressing Enter or Space on a focused chunk,
  selects it.
- Where near-duplicates were removed, a muted line "<n> near-duplicate
  chunks removed" appears.

Footer:
- "Chunk <i> of <N>".
- Prev and Next buttons, disabled at the ends.

Keys and states:
- The arrow keys move the selection outside text fields.
- Escape (through the overlay stack), the close button, or a backdrop
  click closes the dialog and returns focus to the card that opened it.
- While the view loads, the dialog SHALL show the loading line and
  skeleton rows of scenario `source-loading`, and Prev and Next are
  disabled.
- A load error SHALL show the error inline with a Retry button.
- For a truncated source, the dialog SHALL show the warning note at the
  top and the "Fetch stopped here" end marker after the last chunk
  (scenario `source-truncated`).
- Below 720px the dialog SHALL be a full-screen sheet with 44px buttons
  and 14px chunk text.
- While the run is active, the dialog SHALL reload the view when a stage
  finishes, and keep the selected chunk.

#### Scenario: Open from a card
- **WHEN** the user clicks the "query cap" card scored 0.65 in the finished run's Passages panel
- **THEN** the Source dialog opens with that chunk highlighted and in view, the why line "Scored 0.65 in q1 but ranked 11 of 14 above 0.50; q1 keeps only its top 10.", and the q1 chip outlined

#### Scenario: Retarget and navigate
- **WHEN** the dialog shows chunk 3 of 9 and the user clicks chunk 5, then presses ArrowUp
- **THEN** chunk 5 is selected and the header shows its fate, then chunk 4 is selected and the footer reads "Chunk 4 of 9"

#### Scenario: Prefiltered chunk
- **WHEN** the user selects a chunk that no sub-query kept after prefilter
- **THEN** its badge reads "prefiltered", it shows no score, and the why line reads "Not scored: outside the top 50 for every sub-query."

#### Scenario: Escape returns focus
- **WHEN** the dialog was opened from a card with the keyboard and the user presses Escape
- **THEN** the dialog closes and focus is back on that card

#### Scenario: Attached file
- **WHEN** the user opens a passage from an attached file
- **THEN** the header shows the file name and "Attached file · no URL" and no "Open original" link

#### Scenario: Truncated fetch
- **WHEN** the source's page was cut by the fetch character limit
- **THEN** the dialog shows the truncation note above the chunks and the end marker after the last chunk

#### Scenario: Phone sheet
- **WHEN** the viewport is narrower than 720px and the user opens a passage
- **THEN** the dialog fills the screen and its buttons are 44px tall

### Requirement: Streaming report panel
The Live run screen (scenario `live`) SHALL render the report markdown as
it streams, with headings, lists, citation chips, and a blinking accent
caret at the end while writing. The panel SHALL keep scrolled to the bottom
while the user is within 140px of it. The header SHALL show "writing · N
tokens" while writing and the writing options (tone, words, language) on
desktop. Before writing it SHALL show the prototype's waiting texts.

#### Scenario: Auto-scroll
- **WHEN** text arrives and the panel is scrolled to within 140px of the bottom
- **THEN** the panel scrolls to the bottom

### Requirement: Live footer
The Live run screen (scenario `live`) SHALL show a footer with elapsed time
(`m:ss`), "<in> in · <out> out" tokens, the cost (`$0.0024`, or "$0.0000 ·
local" when zero), and the connection state with its dot: Connecting,
Connected, Reconnecting, Replaying, or "Closed · run ended", plus
"seq <n>" on desktop.

#### Scenario: Local run
- **WHEN** every stage reports zero cost
- **THEN** the footer shows "$0.0000 · local"

### Requirement: Phone live layout
Below 720px wide (scenario `live` with `device=phone`), the Live run screen
SHALL show the tabs Progress (timeline and sub-queries), Sources, Passages,
and Report with their counts, one tab at a time, with the selected tab
styled as in the prototype.

#### Scenario: Phone tabs
- **WHEN** the user taps Passages on a 390px wide window
- **THEN** only the Passages panel is shown and the tab is marked selected

### Requirement: Queued state
While the connection is opening, the Live run screen SHALL show the
prototype scenario `loading`: tag Connecting, the banner "Connecting to
<ws origin>…", six shimmering skeleton rows in Sources, "Waiting for the
planner…" in Sub-queries, "Waiting for the run to start." in Passages, and
every phase pending. After `run.queued` until `run.started`, the screen
SHALL show the prototype scenarios `queued` and `queued-cli`: the same
skeleton panels and pending phases, the status tag "Queued" with no pulse,
and the banner with the hourglass icon whose text comes from the latest
`run.queued` data. Let N be the number of `held` runs, C the number with
origin `cli`, and W = N − C (every run not from the CLI counts as web).
The place is "Next in line." for position 1, otherwise "<position>nd in
line.", "<position>rd in line.", or "<position>th in line." (2nd, 3rd,
then th). When C < N the text SHALL be "Waiting for a free slot: <N> of
<limit> in use (<W> web, <C> CLI). <place>", leaving out a zero part
("(1 web)", "(2 CLI)"). When C = N the text SHALL be "Waiting for a free
slot: <N> of <limit> in use, all by CLI runs an agent started on this
machine. <place> This run starts as soon as one of them finishes or is
cancelled." Below the text the banner SHALL list each held run: an accent
dot, its run id in monospace, the origin with its icon (terminal window
and "CLI", or browser and "web"), and "· running <m:ss>" counted from its
`started` time.

#### Scenario: Queued
- **WHEN** `run.queued` with position 1, limit 2, and one web and one CLI holder is the last applied event (scenario `queued`)
- **THEN** the tag reads Queued and the banner says "Waiting for a free slot: 2 of 2 in use (1 web, 1 CLI). Next in line." with both holders listed

#### Scenario: Queued behind CLI runs only
- **WHEN** both holders have origin `cli` (scenario `queued-cli`)
- **THEN** the banner says "Waiting for a free slot: 2 of 2 in use, all by CLI runs an agent started on this machine. Next in line. This run starts as soon as one of them finishes or is cancelled."

#### Scenario: Connecting
- **WHEN** the event socket is opening and no `run.queued` has arrived
- **THEN** the screen shows scenario `loading` with the tag Connecting

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

### Requirement: Failure state
When the run fails, or the server reports it `interrupted` (tag
"Interrupted", error "The run stopped without a final event."), the Live
run screen SHALL show the prototype scenario `failure`: tag Failed, the failed phase with its error, Rerun in the
header, and in the Report panel an alert card "Run failed at <Stage>" with
the error text, the hint that earlier stages are kept, and the buttons
"Retry from <Stage>" (fork from the failed stage), "Use cloud profile" (the
same fork with profile `cloud`; shown only when a `cloud` profile exists
and the run used another), and "Copy error". A retry SHALL open the new run
on the Live run screen.

#### Scenario: Retry from Score
- **WHEN** the run failed at score and the user presses "Retry from Score"
- **THEN** `POST /api/runs/{id}/fork` is sent with `from` = `score` and the new run is shown live

### Requirement: Cancelled state
When the run is cancelled, the Live run screen SHALL show the prototype
scenario `cancelled`: tag Cancelled, the banner "Cancelled at <Stage> after
m:ss. Completed stages are kept; nothing was written.", the running phase
cancelled, unfetched sources "not fetched", the Passages text "Cancelled
before scoring." and the Report text "Cancelled before the write stage.
Nothing was written." when those stages had not run, and Rerun.

#### Scenario: Cancel during fetch
- **WHEN** `run.cancelled` arrives while fetch runs
- **THEN** the banner names Fetch and sources not yet fetched show "not fetched"

### Requirement: No run state
When Live run is opened with no followed run, the screen SHALL show the
prototype scenario `empty`: pulse icon, "No run in progress", the
explanatory text, and a "New run" button with the "Alt 1" hint.

#### Scenario: Nothing to follow
- **WHEN** there is no queued or running run and the user presses Alt+2
- **THEN** "No run in progress" and the "New run" button are shown

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

### Requirement: Report screen
The Report screen SHALL match the prototype scenario `finished`: Completed
tag, run id, meta `date · duration · recipe · N sources · N passages`, the
query as H1, the actions Rewrite (followed by its help button), Copy
markdown, the downloads (Requirement: Export), Copy JSON (context), and
Live view (a secondary button with the Live run nav icon, pulse, that shows
the Live run screen for the same run at `#/live/<run id>`; an addition to
the prototype, offered for every recipe), the line "Written with
<Tone> · <N> words · <Language> · <citation marker label> · <reference
style> [· custom instructions]" (for recipe `answer`, scenario
`finished-answer`: "Answer, at most <N> words · <Tone> · <Language> ·
<citation marker label> · <reference style> [· custom instructions]"), the report (headings, lists, citation
chips), then the heading "References" (19px) followed by the reference
style name (12px, muted) and the reference style help button, with the
report's reference entries below it, and an aside with Sources (count
fetched and failed, "N kept", the citation labels that use each source)
and Selected passages (label, score, heading path, text, domain). A run
with recipe `context` SHALL show the selected passages in place of the
report and SHALL NOT offer Rewrite, Copy markdown, or any download. A run
with recipe `answer` SHALL use the same layout, actions, and References as
a report (scenario `finished-answer`).

A query of 240 characters or fewer SHALL show as the full H1, with no
clamp and no button (scenarios `finished` and `report-cut`). When the query
is longer than 240 characters (scenario `long-brief`), the H1 SHALL be
clamped to three lines and followed by the same "Show full question · <N> characters" /
"Show less" button as the Live run header (Requirement: Live run header).
Expanded, the H1 SHALL show the whole query at 15px regular weight, line
breaks kept, in a tinted box no taller than the smaller of 50% of the
viewport and 480px that scrolls inside itself.

#### Scenario: Finished report
- **WHEN** the user opens a completed report run
- **THEN** the report, the sources with kept counts, and the selected passages are shown

#### Scenario: Live view from the report
- **WHEN** the user presses Live view on the Report screen of run `r_7d11`
- **THEN** the Live run screen is shown for `r_7d11` (`#/live/r_7d11`) with its full phase timeline

#### Scenario: Live view on a context run
- **WHEN** the user opens a completed run with recipe `context`
- **THEN** Live view is offered next to Copy JSON (context), and Rewrite, Copy markdown, and the downloads are not

#### Scenario: Finished answer
- **WHEN** the user opens a completed run with `writing.format` = `answer` and words 400 (scenario `finished-answer`)
- **THEN** the meta line names `answer`, the options line starts "Answer, at most 400 words ·", and the answer is shown with its citation chips, References, Rewrite, Copy markdown, and the same downloads as a report

#### Scenario: Long question title
- **WHEN** the user opens the report of a run whose query has 4,030 characters
- **THEN** the title shows three lines of the query and "Show full question · 4,030 characters"; pressing it shows the whole query in a scrolling box

#### Scenario: Short question title
- **WHEN** the user opens the report of a run whose query has 120 characters
- **THEN** the title shows the whole query, not clamped, and no "Show full question" button

#### Scenario: References heading
- **WHEN** the run's reference style is `MLA`
- **THEN** the heading reads "References" followed by "MLA" and a help button, and the "Written with" line ends with "· MLA"

### Requirement: Report continuation notes
The Report screen SHALL show the report's continuation state between the
"Written with" line and the report, as in the prototype:

- When the report has `continuations` of 1 or more and is not truncated
  (scenario `finished`), it SHALL show a muted line with the bend-arrow
  icon: "Continued <N>× after reaching the output limit.", followed by a
  help button. The button's label is "Continued", its title "Continued",
  and its body "The writer reached its output limit, so it was asked to
  continue from where it stopped. The parts are joined into one report."
- When the report is truncated (scenario `report-cut`), it SHALL show the
  warn-styled note with the scissors icon (dashed warn border, warn tint):
  "Still cut off after <N> continuations. The last section may be
  incomplete." When N is 0, the note reads "Cut off at the output limit.
  The last section may be incomplete." After the last block of the report
  and before References, it SHALL show the warn-coloured end marker with
  the scissors icon, "Output limit reached here".
- A report with no continuations that is not truncated SHALL show neither.

The notes SHALL use the Nocturne variables only.

#### Scenario: Continued report
- **WHEN** the user opens a report with `continuations` 1 and `truncated` false
- **THEN** the screen shows "Continued 1× after reaching the output limit." with its help button, and no cut note or end marker

#### Scenario: Cut report
- **WHEN** the user opens a report with `continuations` 2 and `truncated` true
- **THEN** the screen shows "Still cut off after 2 continuations. The last section may be incomplete." above the report and "Output limit reached here" after its last block

#### Scenario: Cut without continuation
- **WHEN** the user opens a report with `continuations` 0 and `truncated` true
- **THEN** the note reads "Cut off at the output limit. The last section may be incomplete." and the end marker is shown

#### Scenario: Normal report
- **WHEN** the user opens a report with `continuations` 0 and `truncated` false
- **THEN** no continuation note, cut note, or end marker is shown

### Requirement: Citations
Citations in the report SHALL render as citation chips, one per cited
passage (a group `[1, 2]` gives two chips), labelled per the run's citation
marker: `[n]` for numeric, superscript digits for superscript, and
"Author, Year" for author-year, where the author is the source's author,
else the web host without `www.`, else the file name, and the year is the
source's year, else "n.d.". Chips SHALL be built from the report body with
`[n]` markers (the streamed text while writing, the body of the run's
`report.json` once written), and the finished report SHALL be followed by
its References list. Hovering or focusing a chip (scenarios `live` and
`finished`) SHALL show the prototype's tooltip for passage `n` from the
run's `context.json`: label, display score with a bar, "relevance", the
quoted passage text, the source title, and `domain · heading path`; below
the chip, or above it when less than 230px remain below. Leaving,
blurring, or Escape SHALL hide it.

#### Scenario: Hover a citation
- **WHEN** the user hovers the chip for [3]
- **THEN** the tooltip shows passage 3's text, its source title and domain, and its score

### Requirement: Report tables
Report markdown on the Live run panel (scenario `live`) and the Report
screen (scenario `finished`) SHALL render GitHub-style pipe tables as
tables, styled with the design system's table style (header row, cell
padding, row dividers). A table wider than the report SHALL scroll sideways
inside its own area; the page and the panel SHALL NOT scroll sideways.
Citation markers inside table cells SHALL render as citation chips.

#### Scenario: Pipe table in a report
- **WHEN** the report contains a header row, a `|---|---|` separator row, and three body rows
- **THEN** the report shows a table with one header row and three body rows

#### Scenario: Citation in a cell
- **WHEN** a table cell contains "$0.50–$2 [13]"
- **THEN** the cell shows the text and a citation chip for passage 13

#### Scenario: Wide table
- **WHEN** a table is wider than the Live run report panel
- **THEN** only the table area scrolls sideways

### Requirement: Export
On the Report screen (scenario `finished`), "Copy markdown" SHALL copy the
report, the downloads SHALL save the report as Markdown, PDF, or Word, and
"Copy JSON (context)" SHALL copy `{run, parent, query, options: {recipe,
sources, profile, writing}, passages: [{cite, score, source, heading_path,
text}]}`.

- "Download .md" SHALL save `<run id>.md` with `# <query>` and a blank line
  before the report, built in the browser.
- "Download .pdf" and "Download .docx" SHALL fetch `GET
  /api/runs/{id}/export?format=pdf|docx` and save `<run id>.pdf` or
  `<run id>.docx`.

Layout, as in the prototype's `downloads` tweak set to `auto`: on desktop
(scenarios `finished`, `report-cut`, `finished-answer`) the three downloads
SHALL be three secondary buttons in that order, each with the
download-simple icon and the label "Download .md", "Download .pdf", or
"Download .docx", placed between Copy markdown and Copy JSON (context). On a
phone they SHALL be one secondary "Download" button with the download-simple
icon and a caret-down icon (`aria-haspopup="menu"`, `aria-expanded`) that
opens a menu labelled "Download format" below it (scenario `export-menu`),
with one item per format: a muted file icon (file-text, file-pdf,
file-doc), the extension in the mono font (`.md`, `.pdf`, `.docx`), and a
muted description ("Markdown", "PDF", "Word"); items are 44px tall on a
phone. Choosing an item SHALL close the menu and start that download;
Escape or a click outside SHALL close it.

While a PDF or DOCX export is in progress (scenario `export-busy`), its
button, or the phone's "Download" button, SHALL show a spinning
circle-notch icon and "Exporting…", carry `aria-busy="true"`, and be
disabled; the other desktop buttons stay usable. On success the toast SHALL
read "Downloaded <id>.<ext>". A failed export (scenario `export-error`)
SHALL save nothing and show an error toast with the warning-circle icon in
the danger color and the response's `detail` (for example "PDF export
needs typst on the server"). "Copy markdown" and "Copy JSON (context)"
SHALL confirm with the toasts "Markdown copied" and "Context JSON copied".
Runs with recipe `context` SHALL show no downloads.

#### Scenario: Download
- **WHEN** the user presses "Download .md" on run `r_8c21`
- **THEN** a file `r_8c21.md` starting with `# <query>` is saved and the toast "Downloaded r_8c21.md" shows

#### Scenario: Download PDF on desktop
- **WHEN** the user presses "Download .pdf" on run `r_8c21` on desktop
- **THEN** that button shows "Exporting…" and is disabled until the response arrives, then `r_8c21.pdf` is saved and the toast "Downloaded r_8c21.pdf" shows

#### Scenario: Phone menu
- **WHEN** the user opens run `r_8c21`'s Report screen on a phone and presses "Download"
- **THEN** a menu "Download format" lists `.md` Markdown, `.pdf` PDF, and `.docx` Word, and choosing `.docx` closes it and saves `r_8c21.docx`

#### Scenario: Export unavailable
- **WHEN** the user presses "Download .pdf" and the server answers 503 `export_unavailable` with detail "PDF export needs typst on the server"
- **THEN** no file is saved and an error toast with the danger-colored warning icon shows "PDF export needs typst on the server"

#### Scenario: Context run
- **WHEN** the user opens a run with recipe `context`
- **THEN** no download button or menu is shown

### Requirement: Rewrite
Rewrite on the Report screen (scenarios `finished` and `versions`) SHALL
open the prototype's "Rewrite report" dialog, prefilled with the viewed
version's writing options. Above the writing fields the dialog SHALL show a
Format field (segmented, `report` then `answer`, scenario `rewrite-format`)
set to the viewed version's format, followed by its help button. The
dialog SHALL mark each changed field "changed" with "was
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

#### Scenario: Rewrite as an answer
- **WHEN** the user opens Rewrite on a report, picks Format `answer` and length 400, and confirms (scenario `rewrite-format`)
- **THEN** Format shows "changed" with "was report" and Reset, and `POST /api/runs/{id}/fork` is sent with `from` = `write` and `writing` containing `format` = `answer` and `words` = 400

#### Scenario: Rewrite an older version
- **WHEN** the user views v1 of a lineage that has v1 and v2 and opens Rewrite
- **THEN** the dialog says "Creates v3", and the created run has version 3

### Requirement: Versions
When the viewed run has other runs in its lineage, the Report screen SHALL
show the prototype scenario `versions`: the "Versions" nav with one button
per run in the lineage, oldest first, each with "v<N> · <kind>", its id,
and a description (the full run's duration, or the writing options changed
against its parent plus duration), the viewed one marked current; and above
the report the note "Rewritten from <parent id> (v<N>): same sources and
passages; changed <changes>." Pressing a version SHALL show that run's
report. A single-run lineage SHALL show no Versions nav.

#### Scenario: Two versions
- **WHEN** the user views `r_8c4e`, a rewrite of `r_8c21` with tone concise and 250 words
- **THEN** the nav shows v1 and v2 with v2 current, and the parent note names `r_8c21` and the changes

### Requirement: Run help placements
The run screens SHALL place help buttons (web-shell "Inline help") where
the prototype places them, with these titles and bodies verbatim (the
accessible label is "Help: <label>"):

| Placement | Label | Title | Body | Example |
|---|---|---|---|---|
| New run, after "Attachments" | Attachments | Attachments | Markdown or text files to research alongside the web, or instead of it. | pdf-ingest output (.md) |
| Options, after "Recipe" | Recipe | Recipe | Report writes a cited report. Answer replies to the question directly, with citations, in at most the chosen length. Context stops after selecting passages and returns them with sources and scores, for agents or your own answer. Faster and cheaper. | |
| Options, after "Sources" | Sources | Sources | Web searches the internet. Files uses only your attachments. Both combines them; attachments get a share of the context budget. | |
| Options, after "Profile" | Profile | Profile | A saved choice of providers and model. Advanced shows its values; edits apply to this run only. | |
| Options, after an "overridden" mark | Overridden | Overridden | This value differs from your default in Settings and applies to this run only. | |
| Rewrite dialog, after a "changed" mark | Changed | Changed | This value differs from the version you are rewriting. | |
| Sub-queries and Research rounds, after the "Topic line" label on the `q0` row | Topic line | Topic line | A short topic the planner writes from your question. Passages are ranked against it as the first query, q0. Questions up to 200 characters are searched as written; longer ones are searched by this topic. | |
| Phase card Plan | Plan | Plan | Splits your question into focused sub-queries for search. | |
| Phase card Search | Search | Search | Runs each sub-query against the search provider and collects candidate URLs. | |
| Phase card Fetch | Fetch | Fetch | Downloads each URL and extracts its readable text. Failed pages are skipped and the run continues. | |
| Phase card Load | Load | Load | Reads your attached files. | |
| Phase card Chunk | Chunk | Chunk | Splits pages and files into passages along their headings. | |
| Phase card Prefilter | Prefilter | Prefilter | Quickly narrows chunks with embeddings or keyword ranking before the slower scorer. | |
| Phase card Score | Score | Score | Rates how useful each passage is for its question. | |
| Phase card Select | Select | Select | Picks the best passages that fit the writer's context budget. | |
| Phase card Write | Write | Write | Writes the report from the selected passages and cites each claim. | |
| Device chip | Device | Device | The machine and GPU running the current stage, as labelled in the profile. | desktop:gpu0 |
| Header, after Rerun | Rerun | Rerun | Starts a fresh run with the same question and attachments. | |
| Passages header, after the scorer tag | Scorer | Scorer | Which scorer ranked the passages. “fallback” means the configured scorer failed and a simpler one took over. | jev · rerank · bm25 · fallback |
| Passages funnel, chunks step | <n> chunks | Chunks | Pages and files split along their headings. The prefilter ranks them per sub-query and passes the top <P> of each to the scorer; the rest are “prefiltered” and never scored. | |
| Passages funnel, scored step | <n> scored | Scored | Chunks the scorer rated from 0 to 1, after the prefilter. | |
| Passages funnel, kept step | <n> kept | Kept | Scored at least <T> (threshold) and in the top <K> of their sub-query (query cap). | |
| Passages funnel, cited step | <n> cited | Cited | Kept passages that fit the writer’s selection: at most <S> per source (source cap) and within the token budget. Numbered in the report. | |
| Passages header, after "Fates" | Passage fates | Passage fates | (the fate legend below) | |
| Failure card, after "Retry from Score" | Retry from Score | Retry from Score | Reruns scoring, selection and writing on the saved pages. Useful after changing the scorer or profile. | |
| Live footer, after the cost | Tokens and cost | Tokens and cost | Prompt and completion tokens across all stages. Cost is $0 for local models. | |
| Report, after Rewrite | Rewrite | Rewrite | Writes a new version from the same passages with different writing options. No new search; it creates a linked version. | |
| Report, after "Versions" | Versions | Versions | Reports that share the same research. v1 is the original; rewrites follow. | |
| Report, after the References style | Reference style | Reference style | Format of the reference list at the end of the report: APA, MLA, Chicago or IEEE. | |

In the funnel texts, `<P>` is the run's `score.candidates`, `<T>` the shared
display threshold with two decimals (or "the threshold" when queries
differ), `<K>` the run's `score.top_k`, and `<S>` the run's
`select.max_chunks_per_source`, all from the run's saved configuration.
The "Passage fates" tooltip SHALL show, instead of a body, one row per fate
with its badge icon, its term, and its text:

| Icon | Term | Text |
|---|---|---|
| quotes | cited [n] | Selected and cited in the report. The marker follows your citation setting. |
| stack | source cap | Kept, but its source already has the maximum of <S> cited passages. |
| gauge | over budget | Kept, but too long for the tokens left in the writer’s budget. |
| funnel | query cap · q1 | At or above <T>, but its sub-query already had <K> better passages. |
| arrow-down | below <T> | Scored under the threshold. |
| minus-circle | prefiltered | Never scored: outside the top <P> for every sub-query. Shown in the source view. |

The writing fields of the Options panel and the Rewrite dialog SHALL carry
the writing-field help of web-shell "Shell help placements". A phase card
in the waiting state SHALL use the label "<Phase>, waiting for GPU", the
title "<Phase> · waiting for GPU", and the body "Another model is
unloading from the same GPU. This stage starts when it is free." followed
by a space and the phase's body. When the run failed at a stage other
than score, the failure card's help SHALL use the label and title "Retry
from <Stage>" and the body "Reruns <stage> and the stages after it on the
saved results of earlier stages."

#### Scenario: Waiting phase help
- **WHEN** the Score phase is waiting and the user hovers its help button
- **THEN** the tooltip title is "Score · waiting for GPU" and the body is "Another model is unloading from the same GPU. This stage starts when it is free. Rates how useful each passage is for its question."

#### Scenario: Run option help
- **WHEN** the user opens the Options panel and focuses the help button after "Recipe"
- **THEN** exactly one help button follows the label, and the tooltip shows the Recipe text

#### Scenario: Topic line help
- **WHEN** the user focuses the help button after the "Topic line" label on the `q0` row
- **THEN** the tooltip title is "Topic line" and the body is "A short topic the planner writes from your question. Passages are ranked against it as the first query, q0. Questions up to 200 characters are searched as written; longer ones are searched by this topic."

#### Scenario: Rewrite mark help
- **WHEN** a field in the Rewrite dialog shows "changed" and the user taps the help button after it
- **THEN** the tooltip reads "Changed" and "This value differs from the version you are rewriting."

#### Scenario: Funnel help uses the run's configuration
- **WHEN** a run's configuration has `score.top_k = 10` and every query's display threshold is 0.5, and the user focuses the kept step
- **THEN** the tooltip reads "Kept" and "Scored at least 0.50 (threshold) and in the top 10 of their sub-query (query cap)."

#### Scenario: Fate legend
- **WHEN** the user hovers the help button after "Fates"
- **THEN** the tooltip lists the six fates with their icons, terms, and texts

### Requirement: Depth control
The Options panel SHALL show the Depth group of scenarios `new-depth`,
`new-custom`, `new-preset`, and `new-depth-many`:
- A "Depth" label with its help button.
- A segmented control: Quick, Standard, Deep, Exhaustive, then the user
  presets by name as the server lists them (their label is the name as
  written, for example `wide`), then Custom. Standard is preselected.
  Every preset comes from `GET /api/depths`. With more than three user
  presets, only the first two SHALL be segments; the others SHALL be
  options of a "More…" select placed after them and before Custom, which
  reads "More…" until one of its presets is selected and then shows that
  preset's name, marked selected like a segment (scenario
  `new-depth-many`). The control SHALL wrap onto more rows when it does
  not fit, as in the prototype at phone width.
- Under it, the selected depth's description ("Set every value yourself."
  for Custom).
- An estimate line: "~<P> pages · <R> round(s) · ~<C> LLM calls".
  - R is Rounds, and the word is "round" when R is 1.
  - P is the smaller of Max pages and the sum of two terms:
    (Sub-queries + 1) × Results per query, and (R − 1) × Follow-ups per
    round × Results per query.
  - C is (1 when Sub-queries > 0) + (R − 1) + 1.
- An "Advanced" disclosure ("· <Label> values" for a preset, "· your
  values" for Custom) listing, each with its help button: Sub-queries
  (1-12), Results per query (1-20), Max pages (5-300, step 5), Rounds
  (1-8), Follow-ups per round (1-12), and Passages per query (1-40). Its
  note reads "<Label> preset. Edit any value to switch to Custom." for a
  preset.
  - Follow-ups per round shows the depth's `queries_per_round` from
    `GET /api/depths`. It is disabled with the lock icon and the note
    "Used between rounds; needs 2+ rounds." while Rounds is 1, and its
    help button SHALL read "Follow-ups per round" / "Most follow-up
    searches the gap step writes after each round but the last. Round 1
    searches the sub-queries."
  - With a preset selected, the fields show the preset's values and look
    read-only (dashed, muted), but accept typing. Editing a field switches
    the depth to Custom with the edited values.
  - Picking Custom opens Advanced. Its fields start with the last Custom
    values saved in browser storage, or else with the values of the depth
    selected before.
  - Below the fields, the save actions of Requirement: Save depth and
    profile actions.
- When Sources is `files`, Rounds is disabled with the lock icon at 1 and
  the note "Files-only runs use 1 round.", and the estimate counts 1 round.

The run request SHALL send `depth` set to the preset name and no `research`
for a preset. For Custom it SHALL send `depth` = `custom` and `research`
with all six values. Help texts SHALL be verbatim from the prototype's
help entries `depth`, `d-subq`, `d-rpq`, `d-pages`, `d-rounds`, `d-ppq`,
and `w-words-def`.

#### Scenario: Pick a preset
- **WHEN** the user picks Deep and starts a run
- **THEN** the request has `depth` = `deep` and no `research`

#### Scenario: Pick a user preset
- **WHEN** `GET /api/depths` lists the user preset `wide` and the user picks it (scenario `new-preset`)
- **THEN** the control shows `wide` between Exhaustive and Custom, the description and the Advanced values are `wide`'s, and starting sends `depth` = `wide` and no `research`

#### Scenario: Many user presets
- **WHEN** `GET /api/depths` lists the user presets `lit-review`, `news-scan`, `survey-fast`, and `wide` (scenario `new-depth-many`)
- **THEN** `lit-review` and `news-scan` are segments, a "More…" select after them offers `survey-fast` and `wide`, and picking `wide` there shows `wide` in the select, marked selected

#### Scenario: Edit switches to Custom
- **WHEN** Deep is selected and the user changes Max pages to 80
- **THEN** the control shows Custom, Advanced is open, Max pages is 80, the other fields keep Deep's values, and starting sends `depth` = `custom` with those six values

#### Scenario: No budgets in Depth
- **WHEN** the user opens Depth's Advanced
- **THEN** it shows no Context tokens, Gap context tokens, Model, or thinking field

#### Scenario: Follow-ups per round edited
- **WHEN** Deep is selected and the user changes Follow-ups per round to 6
- **THEN** the control shows Custom, the estimate counts 6 follow-ups per round, and starting sends `research.queries_per_round` = 6

#### Scenario: Follow-ups locked at one round
- **WHEN** Rounds is 1
- **THEN** Follow-ups per round is disabled with "Used between rounds; needs 2+ rounds."

#### Scenario: Custom remembered
- **WHEN** the user started a Custom run with Sub-queries 6, then opens New run again and picks Custom
- **THEN** Sub-queries shows 6

#### Scenario: Rounds disabled
- **WHEN** Sources is `files` and the user opens Advanced
- **THEN** Rounds is disabled at 1 with "Files-only runs use 1 round."

#### Scenario: Deep estimate
- **WHEN** Deep is selected with Sub-queries 6, Results per query 10, Max pages 60, Rounds 3, and Follow-ups per round 3
- **THEN** the estimate line reads "~60 pages · 3 rounds · ~4 LLM calls"

#### Scenario: Auto context
- **WHEN** the user opens Depth's Advanced with Deep selected
- **THEN** no context budget is shown there; Context tokens and its Auto budget are in the profile's Advanced values (Requirement: Profile advanced values)

#### Scenario: Clamped context
- **WHEN** the profile's Context tokens asks more than the model window leaves
- **THEN** the clamp note shows under Context tokens in the profile's Advanced values and the estimate line has no context part

#### Scenario: Auto gap context
- **WHEN** Custom is selected with Rounds 3
- **THEN** the request's `research` has no `gap_context_tokens`; Gap context tokens is sent in `llm` only when edited in the profile's Advanced values

#### Scenario: Gap context locked at one round
- **WHEN** Rounds is 1
- **THEN** Gap context tokens in the profile's Advanced values is disabled with "Used between rounds; needs 2+ rounds."

### Requirement: Depth tags
The Live run header and the Report screen header SHALL show the run's depth
as an outline tag after the status tag ("Quick", "Standard", "Deep",
"Exhaustive", or "Custom"), as in scenarios `live` and `finished`. A run
with no depth SHALL show "Standard".

#### Scenario: Deep run
- **WHEN** the user opens a finished run whose summary has `depth = "deep"`
- **THEN** the Report header shows Completed followed by the tag "Deep"

### Requirement: Research rounds panel
On a multi-round run, the Live run screen SHALL show the "Research rounds"
panel in place of the Sub-queries panel (scenarios `rounds-live`,
`rounds-done`, `rounds-nonew`, `rounds-max`, `rounds-nofollow`). It is built from `plan.ready`,
`hit.found`, `round.done`, `gap.ready`, and `research.done` events.

The panel header shows "Research rounds", its help button (prototype entry
`rounds`), and a summary:
- "up to <N> rounds" before round 1;
- "round <k>/<N>" during a round;
- "gap after round <k>" during a gap step;
- "<ran> of <N> rounds" when research is done;
- "cancelled" when cancelled.

Each round that has started shows:
- An icon (spinner while running, check when done, minus-circle for 0 new
  pages, stop when cancelled), "Round <k>", and the kind ("planner queries"
  for round 1, "gap follow-ups" after).
- A status:
  - "<p> new pages · <kept> kept" when done;
  - "<p> new pages · <searching|fetching|chunking|prefiltering|scoring>"
    while running;
  - "0 new pages · <m> already fetched" for a round with no new pages.
- The gap note written after it, when there is one.
- Under the note, when the gap step after it named missing question parts
  (`gap.ready` missing), the line "Missing: <part>; <part>" in the note's
  muted style, every part in reply order. The prototype has no such
  element; it follows the note's style in every `rounds-*` scenario, dark
  and light, phone and desktop.
- Its queries, each with its ID (`q0`, `q1`, …), text, and status:
  "queued", "searching", or "<n> results". Round 1 starts with `q0`, shown
  as in the Sub-queries panel: the muted label "Topic line" and its help
  button on a line above the topic text (scenarios `rounds-*`). `q0` counts as
  one of round 1's queries. With more than 3 queries, only 2 are shown, plus a
  "+<n> more" button that toggles to "Show fewer". A running round is
  expanded.
- A gap line: "Gap: reading the best passages so far…" with a spinner
  while the gap step runs; after it, "Gap: <n> follow-up queries for round
  <k+1>" with the bend-arrow icon, or "Gap: no usable follow-up query" with
  the pencil-slash icon when the gap step wrote none (scenario
  `rounds-nofollow`). A finished gap line is followed by " · <u> uncovered"
  in the same muted color when the coverage table marked u > 0 queries
  `uncovered` (`gap.ready` uncovered query IDs).

When research is done, a final line shows:
- "All <N> rounds ran · max rounds", or "Stopped after round <ran> of <N> ·
  <reason>";
- the reason's icon (prohibit for no new sources, files for page limit
  reached, pencil-slash for no follow-ups, stack for max rounds,
  warning for gap step failed);
- the "Why research stopped" help button (prototype entry `r-stop`), with
  one row per stop reason, each with its icon: no new sources ("Follow-up
  searches returned only pages already fetched."), page limit reached
  ("Max pages was used up."), `no follow-ups` ("The gap step wrote no
  usable follow-up query, even when asked twice."), max rounds ("Every
  planned round ran."), and `gap step failed` ("The gap step's model call
  failed; the report uses the rounds that ran."); it has no row for
  coverage, because coverage never stops research;
- the end note under it.

While research runs and rounds remain, a dashed line shows "1 more round
to go" or "<m> more rounds to go" (scenario `rounds-live`). Before any round starts, the panel shows "Planning round 1
queries…".

The panel's help texts (`rounds`, `r-stop`) and the Gap phase card help
(`ph-gap`) SHALL be verbatim from the prototype's entries; none of them
says the gap step can end research early.

#### Scenario: Live round
- **WHEN** a three-round run is fetching in round 2 (scenario `rounds-live`)
- **THEN** round 1 shows its pages and kept count, its gap note, and its gap line ending " · <u> uncovered", round 2 shows a spinner with "fetching", and the dashed line "1 more round to go" is shown

#### Scenario: Topic in round 1
- **WHEN** round 1 has `q0` and five planner sub-queries
- **THEN** round 1 lists `q0` first, with the "Topic line" label and its help button above its text, shows two queries plus "+4 more", and "+4 more" reveals `q2` to `q5`

#### Scenario: No new sources
- **WHEN** research stopped after round 3 of 4 because rounds 2 and 3 fetched no new page (scenario `rounds-nonew`)
- **THEN** rounds 2 and 3 show "0 new pages · <m> already fetched", round 2 shows its gap line, and the final line reads "Stopped after round 3 of 4 · no new sources" with the end note "Follow-up searches returned only pages fetched in earlier rounds."

#### Scenario: No follow-ups
- **WHEN** research stopped after round 2 of 3 with `no follow-ups` (scenario `rounds-nofollow`)
- **THEN** round 2's gap line reads "Gap: no usable follow-up query · 2 uncovered" with the pencil-slash icon, and the final line reads "Stopped after round 2 of 3 · no follow-ups" with the pencil-slash icon and the end note "The gap step wrote no usable follow-up query."

#### Scenario: Uncovered on the gap line
- **WHEN** `gap.ready` after round 1 has three follow-ups and uncovered query IDs `q4` and `q6` (scenario `rounds-live`)
- **THEN** round 1's gap line reads "Gap: 3 follow-up queries for round 2 · 2 uncovered"

#### Scenario: Max rounds
- **WHEN** all three rounds ran (scenarios `rounds-done` and `rounds-max`)
- **THEN** the final line reads "All 3 rounds ran · max rounds" with no end note

#### Scenario: Missing parts line
- **WHEN** `gap.ready` after round 1 has the note "Setup is unclear." and missing parts "setup" and "cost" (scenario `rounds-live`)
- **THEN** round 1 shows "Setup is unclear." and under it "Missing: setup; cost" in the note's style

#### Scenario: No missing parts
- **WHEN** `gap.ready` after round 1 has an empty missing list
- **THEN** round 1 shows no "Missing:" line

### Requirement: Source round tags
In a multi-round run, a source in the Live Sources panel that was fetched
in round k > 1 SHALL show the tag "round <k>" under its status, taken from
`page.fetched`.

#### Scenario: Round 2 source
- **WHEN** a page is fetched in round 2
- **THEN** its Sources row shows "round 2"

### Requirement: Report rounds meta
The Report screen meta line of a multi-round run SHALL end with " · <ran> of
<planned> rounds", from the run summary (scenario `finished`).

#### Scenario: Deep report
- **WHEN** a deep run's summary has `rounds_planned` 3 and `rounds_ran` 2
- **THEN** the meta line ends with "· 2 of 3 rounds"

### Requirement: Domain rows
The Run group of the Options panel (scenarios `new-domains` and
`new-domain-error`) SHALL end with the rows "Allow domains" and "Block
domains", each label followed by its help button (Requirement: Domain
help), in the prototype's form grid. Each row SHALL hold a chips input:
- every entry shows as a chip with a remove button labelled
  "Remove <entry>";
- typing or pasting a comma, a space, or a new line, pressing Enter, or
  leaving the input adds the typed text as entries, lowercased, with a
  trailing dot removed, skipping entries already in the list;
- Backspace in an empty input removes the last chip;
- with no chip, the placeholder is "any domain" for Allow and "none" for
  Block;
- under Allow domains the hint "Suffix match: gob.pe also matches
  www.gob.pe." (12px, muted).

Each row SHALL start from its default list: the selected profile's own list
when the profile sets one (`allow_domains` or `block_domains` from `GET
/api/profiles` not null), else the global run default (`GET
/api/settings`). A row SHALL follow its default when the profile or the
default changes, unless the user edited it. A row whose entries differ from
its default SHALL show the "overridden" mark with its help button,
"default: <list>" (entries joined by ", ", or "default: none"), and a Reset
button, as the writing overrides do, and SHALL count in the panel header's
"N overridden". "Reset all to defaults" SHALL stay limited to the writing
fields. The run request SHALL carry `domains.allow` or `domains.block` only
for an overridden row, as the list of its entries; an overridden row with
no entries SHALL send an empty list.

Before sending, the New run screen SHALL check each entry with the server's
rule (lowercase letters, digits, and hyphens in two or more dot-separated
labels, no leading hyphen). An invalid entry SHALL stop the start, open the
Options panel, and show the start error box (Requirement: Start a run) with
the field named. The invalid chip SHALL turn danger-colored with a dashed
border, the row's input SHALL be marked invalid, and the note "Not a
domain: <entry>. Use the domain only, without a path." SHALL show under the
row. A server rejection of a domain list SHALL mark the chip the server
names the same way.

#### Scenario: Profile defaults
- **WHEN** the selected profile has `allow_domains = ["gob.pe", "sbs.gob.pe"]` and `block_domains = null`, and the global Block default is `["facebook.com"]`
- **THEN** Allow domains shows the chips gob.pe and sbs.gob.pe, Block domains shows facebook.com, neither is overridden, and the run request has no `domains`

#### Scenario: Override for one run
- **WHEN** the defaults allow no domain and the user types "gob.pe pj.gob.pe" in Allow domains and starts the run
- **THEN** Allow domains showed "overridden" and "default: none", the header counted 1 overridden, and the request has `domains.allow` = `["gob.pe", "pj.gob.pe"]` and no `domains.block`

#### Scenario: Clear a default list
- **WHEN** the Block default is `["facebook.com"]` and the user removes its chip
- **THEN** the row shows "overridden" and "default: facebook.com", and the request has `domains.block` = `[]`

#### Scenario: Backspace removes the last chip
- **WHEN** Allow domains has gob.pe and sunat.gob.pe and the user presses Backspace in the empty input
- **THEN** only gob.pe remains

#### Scenario: Invalid entry caught before sending
- **WHEN** Allow domains holds `gob.pe/tramites` and the user presses Run research (scenario `new-domain-error`)
- **THEN** no request is sent, the chip turns danger-colored, the note "Not a domain: gob.pe/tramites. Use the domain only, without a path." shows under the row, and the start error box shows "Fix in Options"

#### Scenario: Profile change
- **WHEN** neither row is edited and the user selects another profile
- **THEN** both rows show that profile's lists, or the global defaults for lists it does not set

### Requirement: Domain help
The Options panel and the Settings "Run defaults" section SHALL place help
buttons (web-shell "Inline help") after "Allow domains" and "Block
domains", with these titles, bodies, and examples verbatim (the accessible
label is "Help: <label>"):

| Placement | Label | Title | Body | Example |
|---|---|---|---|---|
| after "Allow domains" | Allow domains | Allow domains | Only search results from these domains and their subdomains are used. Empty allows every domain. Your files are never filtered. | gob.pe, sunat.gob.pe |
| after "Block domains" | Block domains | Block domains | Search results from these domains and their subdomains are dropped, even when they are also allowed. | facebook.com |

#### Scenario: Allow help
- **WHEN** the user focuses the help button after "Allow domains"
- **THEN** the tooltip reads "Allow domains" and "Only search results from these domains and their subdomains are used. Empty allows every domain. Your files are never filtered."

### Requirement: Search card filtered count
When the run's plan and search stages together report a `filtered` count
F > 0 (summed over every round), the Search phase card (scenario
`live-domains`) SHALL show a second muted 11px line under its progress
text, clipped with "…", reading "<F> filtered by domain", with the full
text as its hover title. With F = 0 the card SHALL have no such line. The
line SHALL use the style of the Prefilter card detail line (Requirement:
Prefilter card detail).

#### Scenario: Filtered hits
- **WHEN** the plan stage reports `filtered` 3 and the search stage reports `filtered` 9
- **THEN** the Search card's detail line reads "12 filtered by domain"

#### Scenario: Nothing filtered
- **WHEN** no domain list is set
- **THEN** the Search card has no detail line

### Requirement: Run recipe
Every run screen that names a run's recipe SHALL derive it from the run's
`until` and resolved `writing.format`, with one shared rule: `context`
when `until` is `select`, else `answer` when `writing.format` is
`answer`, else `report`. The Live run header meta (scenario `live`), the
Report screen meta (scenarios `finished` and `finished-answer`), Copy JSON
(context) `options.recipe`, and the Run history Recipe column and filter
(web-shell) SHALL use this rule. A run whose saved writing options have no
`format` SHALL count as `report`.

#### Scenario: Answer meta
- **WHEN** a run has `until` null and `writing.format` = `answer`
- **THEN** the Live run header meta reads `answer · <sources> · <profile>`

#### Scenario: Context wins
- **WHEN** a run has `until` = `select` and `writing.format` = `answer`
- **THEN** its recipe is shown as `context`

### Requirement: Thinking tags
The Live run header and the Report screen header SHALL show, after the
depth tag (Requirement: Depth tags, scenarios `live` and `finished`), one
outline tag per step whose summary `reasoning` level is not `none`, in the
order plan, gap, write, reading "<Step> thinking <level>" with the level
in lower case, for example "Write thinking high". A run with every step at
`none` SHALL show no thinking tag.

#### Scenario: Writer thinking shown
- **WHEN** the user opens a finished run whose summary has `reasoning.write = "high"` and the other steps `none`
- **THEN** the Report header shows Completed, the depth tag, then "Write thinking high"

#### Scenario: No thinking
- **WHEN** a run's summary has every reasoning level `none`
- **THEN** the headers show no thinking tag

### Requirement: Profile advanced values
The Profile row SHALL have an "Advanced" ghost toggle with a caret, as
Depth's (scenarios `new-profile`, `new-profile-over`,
`new-profile-nolimits`), followed by the faint hint "· <profile> values",
or "· <N> changed" when N fields are edited. Opened, it SHALL show the
note "Values from the <profile> profile. Edits apply to this run only.",
or, with edits, "Changed for this run only; the <profile> profile itself
is unchanged." followed by a "Reset to profile" ghost button (counter-
clockwise arrow icon) that removes every edit. Below the note, three
groups, each with an uppercase heading, in the prototype's field grid:
- **Providers**: selects Search, Fetch, Prefilter, Scorer, and LLM, each
  listing that block's entries from `GET /api/providers` by name and
  preselecting the profile's `use`. A block with one entry SHALL be
  disabled with that entry selected and the lock icon note "Only one
  configured."
- **Model**: "Model", a text input with a datalist of
  `GET /api/models?llm=<chosen llm entry>` (free text allowed),
  preselected with the profile's `model` or else the entry's default
  model; "Context window" (1024 to 4194304, step 1024) and "Max output"
  (256 to 4194304, step 1024), preselected with the chosen model's limits
  from the profile's `models` (`GET /api/profiles`), else from the entry's
  (`GET /api/providers`), or with 32768 and 8192 and the info note
  "Fallback: no limits set for this model." when neither lists the model;
  "Plan thinking", "Gap thinking", and "Write thinking" selects with None,
  Low, Medium, High, and Default, preselected with the model's
  `reasoning` from the profile's `models`, else the entry's, or None. Gap
  thinking is disabled with the lock note "Used between rounds; needs 2+
  rounds." while the depth's Rounds is 1.
- **Budgets**: "Context tokens" and "Gap context tokens", number inputs
  (step 1000, min 1000) with the placeholder "Auto", preselected with the
  profile's `context_tokens` and the model's `gap_context_tokens` (from
  the profile's `models`, else the entry's; empty for `auto`). Empty means
  Auto and shows the note "Auto · <budget>". A number above the budget
  shows "<asked> → <budget rounded down to thousands> (model window)". The
  Context tokens budget is the context window minus the profile's
  `prompt_reserve_tokens` minus the output limit, where the output limit
  is the larger of 1024 and twice the words, capped at Max output. The
  Gap context tokens budget is the context window minus
  `prompt_reserve_tokens` minus 768. Both follow the current Length,
  Context window, and Max output. Gap context tokens is disabled with the
  lock note while Rounds is 1.

A Providers field or Context tokens whose value differs from the
profile's value SHALL be drawn solid with a small outline "overridden" tag
and the help button `p-over` beside its label. Model, Context window, Max
output, the three thinking levels, and Gap context tokens SHALL instead
carry a faint source tag after their help button: "edited" (drawn solid)
when the run edits the value, else "from profile" when the profile sets it
(its `llm.model`, or its `models` table for the chosen model), else "from
entry" when the llm entry sets it, else no tag (scenarios
`new-profile-custom`, `new-profile-nolimits`). An unedited field SHALL
look read-only (dashed, muted) but accept typing. A value edited back to
the profile's value SHALL no longer count as edited. Switching the
profile SHALL remove every edit. Switching the LLM entry SHALL set Model
to that entry's default model and remove the edits of Model, Context
window, Max output, the thinking levels, and Gap context tokens; editing
Model SHALL remove the Context window and Max output edits. Below the
groups, the save actions of Requirement: Save depth and profile actions.
Help texts SHALL be verbatim from the prototype's entries `profile`,
`p-search`, `p-fetch`, `p-prefilter`, `p-scorer`, `p-llm`, `p-model`,
`p-limits`, `p-think`, `p-ctx`, `p-gapctx`, and `p-over`.

The run request SHALL send `use` with only the blocks whose entry differs
from the profile's, and `llm` with only the edited fields (`model`,
`context_window`, `max_output_tokens`, `reasoning` steps,
`context_tokens`, `gap_context_tokens`, `"auto"` for an emptied budget).
A run with no edit SHALL send neither. The edits SHALL be kept with the
New run draft while the user moves between screens and cleared after a run
starts.

#### Scenario: Profile values
- **WHEN** the user opens the profile's Advanced for `low-vram` with no edits (scenario `new-profile`)
- **THEN** the hint reads "· low-vram values", Search and Fetch are disabled with "Only one configured.", and Context tokens shows "Auto · 28,368" for the agents/qwen3-14b limits and the default length

#### Scenario: Three edits
- **WHEN** the user changes Scorer to `jev-strict`, Write thinking to High, and Context tokens to 60000 on a 32768-token model (scenario `new-profile-over`)
- **THEN** the hint reads "· 3 changed", Scorer and Context tokens carry "overridden", Write thinking carries "edited", Context tokens shows "60,000 → 32,000 (model window)", and starting sends `use` = `{"score": "jev-strict"}` and `llm` = `{"reasoning": {"write": "high"}, "context_tokens": 60000}`

#### Scenario: Model without limits
- **WHEN** the profile `nixos` uses an llm entry whose default model is not listed in its `models`, and the profile lists none (scenario `new-profile-nolimits`)
- **THEN** Context window shows 32,768 and Max output 8,192, each with "Fallback: no limits set for this model." and no source tag

#### Scenario: Profile tuning shown
- **WHEN** the profile `cloud-rerank` sets `models."claude-sonnet-5-5".reasoning.write = "high"`, its entry lists that model's limits, and the user opens its Advanced
- **THEN** Write thinking shows High with "from profile", and Context window and Max output show the entry's limits with "from entry"

#### Scenario: Reset
- **WHEN** the user presses "Reset to profile"
- **THEN** every field shows the profile's value, no "overridden" or "edited" tag remains, and the hint reads "· <profile> values"

#### Scenario: LLM switch
- **WHEN** the user switches LLM from `agents` to `omniroute`
- **THEN** Model shows `research-smart`, Context window and Max output show that model's limits, and starting sends `use.llm` = `omniroute` without `llm.model`

#### Scenario: Profile switch drops edits
- **WHEN** the user edited Scorer and then selects another profile
- **THEN** every field shows the new profile's values and nothing is marked overridden

#### Scenario: No edits sent
- **WHEN** the user starts a run without editing the profile's Advanced values
- **THEN** the request has no `use` and no `llm`

### Requirement: Profile line in run headers
The Live run header (Requirement: Live run header) and the Report screen
header SHALL show, below the meta line, a profile line: the stack icon,
the run's profile name in the mono font, " · ", and the entries of the
run summary's `use` joined by " · " in the order search, fetch,
prefilter, score, llm, the llm entry followed by "/<model>" (11.5px,
mono, muted). When the summary has `modified = true`, the profile name
SHALL read "custom (<profile>)". On a phone, the line SHALL show only the
profile and "<llm>/<model>", with an "All providers" ghost toggle
(caret-down) that shows the full list and becomes "Fewer" (caret-up),
with `aria-expanded`. A run without `use` (recorded before entries
existed) SHALL show no profile line.

#### Scenario: CLI run with a changed scorer
- **WHEN** a CLI run on `low-vram` used `searxng`, `firecrawl`, `embeddings`, `jev-strict`, and `agents` with model `qwen3-14b`, and its summary has `modified = true` (scenario `live-cli`)
- **THEN** the line reads "custom (low-vram) · searxng · firecrawl · embeddings · jev-strict · agents/qwen3-14b"

#### Scenario: Phone collapse
- **WHEN** the same run is shown at phone width
- **THEN** the line shows "custom (low-vram) · agents/qwen3-14b" and "All providers", and pressing it shows every entry and "Fewer"

### Requirement: Save depth and profile actions
Depth's and the profile's Advanced panels SHALL end with an action row as
in scenarios `new-save-depth`, `new-save-profile`, `new-profile-custom`,
and `new-delete`:
- Depth, with Custom selected: a "Save depth as…" secondary button (plus
  icon). When the Custom values came from editing a user preset (the
  depth selected when the edit switched to Custom), also a "Save to
  <preset>" secondary button (floppy disk icon) before it, or, when that
  preset is managed, the lock note "<preset> is managed by NixOS config"
  instead of that button.
- Depth, with a user preset selected: a "Delete <preset>" ghost button
  (trash icon) at the row's end, or, for a managed preset, only the lock
  note "Managed by NixOS config · read-only". A built-in preset shows no
  action row.
- Profile, with edits: "Save to <profile>" and "Save profile as…", or,
  for a managed profile, the lock note "<profile> is managed by NixOS
  config" and "Save profile as…".
- Profile, without edits: "Delete <profile>", disabled for the active
  profile with the faint reason "The default profile can’t be deleted"
  before it, or, for a managed profile, only the lock note "Managed by
  NixOS config · read-only".

"Save to <preset>" SHALL send `PUT /api/depths/<preset>` with the six
values, Length, and the generated description of Requirement: Save
dialog, then select that preset. "Save to <profile>" SHALL send `PATCH
/api/profiles/<profile>` with the run's edits (the `use` and `llm` a run
request would send), then reload the profiles and clear the edits. Both
SHALL show the toast "Saved depth “<name>”" or "Saved profile “<name>”"
without Undo. Managed, built-in, and active state SHALL come from
`managed`, `source`, and `active` in `GET /api/depths` and
`GET /api/profiles`. A failed request SHALL show its `detail` in an error
toast and change nothing.

#### Scenario: Save to a user preset
- **WHEN** the user selected the user preset `wide`, changed Max pages to 120, and presses "Save to wide"
- **THEN** the client sends `PUT /api/depths/wide`, Depth shows `wide` selected with Max pages 120, and the toast reads "Saved depth “wide”"

#### Scenario: Managed preset edited
- **WHEN** the user edits the managed preset `lit-review` into Custom
- **THEN** the row shows "lit-review is managed by NixOS config" and "Save depth as…", and no "Save to" button

#### Scenario: Save edits into a profile
- **WHEN** the user profile `cloud` has two edits and the user presses "Save to cloud" (scenario `new-profile-custom`)
- **THEN** the client sends `PATCH /api/profiles/cloud` with those edits, the hint reads "· cloud values", and the toast reads "Saved profile “cloud”"

#### Scenario: Active profile not deletable
- **WHEN** the active profile `low-vram` is selected with no edits
- **THEN** "Delete low-vram" is disabled and "The default profile can’t be deleted" shows before it

### Requirement: Save dialog
"Save depth as…" and "Save profile as…" SHALL open the dialog of
scenarios `new-save-depth` and `new-save-profile`: an icon (sliders for a
depth, stack for a profile), the title "Save depth as…" or "Save profile
as…", a close button, and an intro: "Saves the six depth values and the
report length as a new depth. It appears in Depth after the built-in
presets." or "Saves a new profile based on <profile>, with your <N>
edit(s). <profile> itself is unchanged." (without the edits clause when
there are none). Then:
- a "Name" input with the placeholder "e.g. wide-short" or "e.g.
  cloud-rerank" and the hint "Letters, digits, - and _ · up to 64
  characters", replaced by an error with the warning icon once the user
  has typed or submitted: "Enter a name.", "Use 64 characters or fewer.",
  "Use letters, digits, - and _ only.", "Start with a letter or digit.",
  "“<name>” is reserved." (`custom`), "“<name>” is reserved for a built-in
  depth.", or "A <depth|profile> named “<name>” already exists." (ignoring
  case), matching saved-presets "Saved names";
- for a profile, an optional "Description" input (at most 120
  characters, placeholder "One line, shown under the profile");
- a "What is saved" group: for a depth, "Depth values" with the six
  values and Length in words; for a profile, "Entries" (the five blocks),
  "Model and budget" (Model as `<llm entry> / <model>`, Context tokens or
  "Auto · <budget>"), and "Model tuning for <model>" (Context window, Max
  output, Thinking as "plan <level> · gap <level> · write <level>", Gap
  context or "Auto · <budget>") with the info note "Applies only when this
  profile runs <model>. With any other model, that model’s own entry
  limits apply.";
- Cancel and a primary "Save depth" or "Save profile" button (floppy
  disk icon). Escape and a backdrop click close the dialog.

Saving a depth SHALL send `POST /api/depths` with the name, the six
values, Length, and the description "Your preset: <S> sub-queries, <R>
round(s), <W> words." (W with thousands separators), then select the new
preset. Saving a profile SHALL send `POST /api/profiles` with the name,
`from` = the selected profile, the description (or "Based on
<profile>." when empty), and the run's edits, then reload the profiles,
select the new one, and clear the edits. Each SHALL close the dialog and
show "Saved depth “<name>”" or "Saved profile “<name>”". An error answer
SHALL keep the dialog open and show its `detail` as the name error.

#### Scenario: Save a depth
- **WHEN** Custom has Sub-queries 10 and Rounds 1, Length is 1500, and the user saves it as `wide-short` (scenario `new-save-depth`)
- **THEN** the client posts the depth with description "Your preset: 10 sub-queries, 1 round, 1,500 words.", Depth shows `wide-short` selected, and the toast reads "Saved depth “wide-short”"

#### Scenario: Save a profile
- **WHEN** the profile `cloud` has the edits Scorer `rerank`, Write thinking Medium, and Context tokens 120000, and the user saves it as `cloud-rerank` with the description "Hosted models with the local reranker." (scenario `new-save-profile`)
- **THEN** the client posts `from` = `cloud` with `use.score` = `rerank` and those `llm` edits, Profile shows `cloud-rerank` with no edits, and the toast reads "Saved profile “cloud-rerank”"

#### Scenario: Name taken
- **WHEN** the user types `Wide` while the preset `wide` exists
- **THEN** the dialog shows "A depth named “Wide” already exists." and Save does not send a request

### Requirement: Delete dialog
"Delete <name>" SHALL open the alert dialog of scenario `new-delete`: the
title "Delete <depth|profile> “<name>”?", the body "Runs that used it keep
the values they ran with." followed, when the item is selected, by " Depth
switches to Standard." or " New run switches to <active profile>.", and
" This can’t be undone.", then Cancel and a "Delete <depth|profile>"
button (trash icon). Confirming SHALL send `DELETE /api/depths/<name>` or
`DELETE /api/profiles/<name>`, reload the list, switch a selected item as
the body says, and show the toast "Deleted <depth|profile> “<name>”".

#### Scenario: Delete the selected preset
- **WHEN** the user preset `wide` is selected and the user confirms "Delete depth" (scenario `new-delete`)
- **THEN** the client sends `DELETE /api/depths/wide`, Depth shows Standard, `wide` is no longer offered, and the toast reads "Deleted depth “wide”"

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
<sources> · <profile or custom (profile)> · <N> words", the paperclip
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
Attachments). Values come from the run summary's `form`; a run without
`form` fills the question, Sources, Recipe, profile, and Depth from its
summary. When the form had a question or edits before, the toast "Filled
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

### Requirement: Time per stage
Each phase card's time row (mono, 11px) SHALL show:
- "—" (faint) for a pending or reused phase;
- "skipped" (faint) for a skipped phase;
- while waiting for the GPU, "—" and the wait so far in a warn chip with
  the CPU icon;
- otherwise the stage's time: the sum of its `stage.done` `seconds` over
  its rounds, plus, while it runs, the time since its `stage.started`,
  counting up (accent while running, danger when failed), followed by a
  warn chip "+<wait>" when it waited for the GPU at least 0.05 s (from
  `resource.waiting` to the stage's `stage.started`).

The row's title SHALL be "Stage time <t>", or "Round 1 <a> · Round 2 <b> ·
total <t>" for a stage that ran more than one round, plus " · plus <w>
waiting for the GPU" when it waited. Times SHALL read "<s.s>s" under a
minute and "<m>m <ss>s" from a minute on.

Below the timeline, a "Time per stage" section (scenarios `live`,
`done-quick`) SHALL show the timer icon, "Time", its help button (`time`),
the total, and "so far" while the run is running; an 8px stacked bar of
the queue time (`run.started` minus the run's creation time, muted
stripes), each GPU wait (warn stripes, before its stage), and each stage
that ran (the prototype's per-stage colors), each segment as wide as its
share of the total (at least 2px), titled "<label> · <time> · <percent>";
the three largest parts (GPU wait summed) with color, label, time, and
percent ("<1%" for a share under one percent); and an "All stages" ghost
toggle (caret-down, "Fewer" with caret-up when open) that lists Queue
("waiting for a free run slot"), every phase in order ("skipped" for a
skipped one, "<label> · running" for the running one, and the per-round
times "a + b + c" under a stage with several rounds), and "GPU wait" with
"before <stages>". The bar SHALL fill its track at any point of the run.
The Report screen's aside SHALL show, above Sources, "Time <total>" with
its help button, the bar, and the full list for a finished run. The help
text SHALL be verbatim from the prototype's `time` entry.

#### Scenario: Finished quick run
- **WHEN** a finished web-only quick run has plan 14.4s, search 12.9s, fetch 10.7s, chunk 0.2s, prefilter 0.1s, score 3.3s, select 0.0s, and write 11.9s (scenario `done-quick`)
- **THEN** the Plan card's time row reads "14.4s", Load reads "skipped", and the time section's total reads "53.5s" with Plan, Search, and Write as the three largest parts

#### Scenario: Running stage
- **WHEN** the fetch stage started 8 seconds ago and has not finished
- **THEN** the Fetch card's time row reads about "8.0s" in the accent color and counts up, and the time section shows "so far"

#### Scenario: GPU wait
- **WHEN** the score stage waited 4.8 seconds for prefilter to unload and then ran 3.3 seconds
- **THEN** the Score card reads "3.3s" with the chip "+4.8s", and the all-stages list has "GPU wait 4.8s" with "before Score"

#### Scenario: Several rounds
- **WHEN** the search stage ran three rounds of 4.1s, 3.0s, and 2.2s
- **THEN** the Search card reads "9.3s" titled "Round 1 4.1s · Round 2 3.0s · Round 3 2.2s · total 9.3s", and its all-stages entry shows "4.1s + 3.0s + 2.2s"

#### Scenario: Report aside
- **WHEN** the user opens the report of a finished run
- **THEN** the aside shows "Time" with the run's total, the bar, and every phase's time

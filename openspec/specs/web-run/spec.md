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
Cmd+Enter in the question SHALL submit.

#### Scenario: Blank question
- **WHEN** the question contains only spaces
- **THEN** "Run research" is disabled and Ctrl+Enter does nothing

#### Scenario: Submit with the keyboard
- **WHEN** the user types a question and presses Ctrl+Enter
- **THEN** the run is started as if "Run research" was pressed

### Requirement: Attachments
The New run screen (scenario `new`) SHALL offer the prototype's drop zone:
click, Enter, or Space opens the file picker; dragging files over it
highlights it; dropping or picking adds the files. Only `.md` and `.txt`
files SHALL be added; others SHALL be skipped with the alert "Skipped
<names> — only .md and .txt are supported." A file with the name of an
already added file SHALL be ignored. Added files SHALL be listed with name,
size (`B` or `KB` with one decimal), and a remove button.

#### Scenario: Mixed drop
- **WHEN** the user drops `notes.md` and `paper.pdf`
- **THEN** `notes.md` is listed and the alert says `paper.pdf` was skipped

#### Scenario: Remove
- **WHEN** the user presses the remove button of `notes.md`
- **THEN** `notes.md` is no longer listed

### Requirement: Run options
The New run screen (scenario `new`) SHALL show the collapsible "Options"
panel, collapsed by default, whose header shows a summary of every value.
The Run group SHALL offer Recipe (`report`, `context`), Sources (`web`,
`files`, `both`), and Profile (the profiles from `GET /api/profiles`, the active
one preselected). Recipe `context` SHALL start the run with `until` set to
`select`, so no report is written.

#### Scenario: Context recipe
- **WHEN** the user picks Recipe `context` and starts a run
- **THEN** the run request has `until` = `select`

### Requirement: Writing overrides
The Writing group of the Options panel (scenario `new`) SHALL start from
the saved writing defaults. A field whose value differs from its default
SHALL show the "overridden" mark, "default: <value>", and a Reset button;
the panel header SHALL show "N overridden" and the group SHALL offer "Reset
all to defaults" while any field is overridden, and an "edit defaults" link
to Settings. When a default changes in Settings, the New run value of that
field SHALL follow it unless it is overridden. The run request SHALL carry
only the overridden writing fields.

#### Scenario: One override
- **WHEN** the default length is 1200 and the user sets 600
- **THEN** Target length shows "overridden" and "default: 1200 words", the header shows "1 overridden", and the request sends `words` 600 and no other writing field

#### Scenario: Default follows Settings
- **WHEN** the tone is not overridden and the user changes the default tone in Settings
- **THEN** the New run tone shows the new default without an "overridden" mark

### Requirement: Start a run
Starting a run SHALL send `POST /api/runs` with the question, the run options,
the overridden writing fields, and the attachments, then show the new run
on the Live run screen and make it the followed run. When the server
rejects the request, the New run screen SHALL keep every input and show the
server's message.

#### Scenario: Started
- **WHEN** the server accepts the run and returns its id
- **THEN** the Live run screen shows that run with status Connecting

### Requirement: Live run header
The Live run screen (scenario `live`) SHALL show a header with the status
tag (Connecting, Running, Completed, Failed, Cancelled, with the
prototype's tints and pulses), a "rewrite of <id>" tag for a fork from the
write stage, the run id, the meta line `recipe · sources · profile [· N
files]`, and the query clamped to two lines. Actions: Cancel while queued
or running, "Open report" when completed, Rerun when failed or cancelled.
Cancel SHALL send `POST /api/runs/{id}/cancel`. Rerun SHALL send
`POST /api/runs/{id}/rerun` (same request and attachments, a new run) and
show the new run on the Live run screen.

#### Scenario: Completed
- **WHEN** `run.done` is applied (end of scenario `live`)
- **THEN** the tag reads Completed, Cancel is gone, and "Open report" opens the Report screen

### Requirement: Phase timeline
The Live run screen (scenario `live`) SHALL show the nine phases Plan,
Search, Fetch, Load, Chunk, Prefilter, Score, Select, and Write as the
prototype's cards, each with icon, label, progress text, and a 3px progress
bar, styled per state: pending, waiting (warn dashed border, stripes, CPU
icon, text "waiting for GPU · <reason>"), running (accent, spinning icon,
glow), done, reused ("reused from <parent id>"), failed (danger, with the
error), and cancelled. Waiting SHALL never look like running. Phases that a
run's recipe skips SHALL show done with "skipped".

#### Scenario: Waiting for a device
- **WHEN** the score stage has `resource.waiting` with released stage `prefilter` and has not started
- **THEN** the Score card shows the waiting style and "waiting for GPU · prefilter unloading"

### Requirement: Device chip
On desktop, while the run is queued or running and any stage has a device
label, the Live run header (scenario `live`) SHALL show the prototype's
device chip with only labels: "<stage> · <device>" while a stage with a
device runs (accent icon), "<device> · swapping models" while one waits
(warn icon), and "<device> · idle" otherwise (faint icon). It SHALL show no
memory figures.

#### Scenario: Scorer running
- **WHEN** the score stage runs on device `desktop:gpu0`
- **THEN** the chip reads "score · desktop:gpu0" and shows no memory figure

### Requirement: Sub-queries and sources panels
The Live run screen (scenario `live`) SHALL show the Sub-queries panel
(number, text, status queued, searching, "N results", reused, or
cancelled; summary `done/total`) and the Sources panel, newest first, each
row with icon, title linking to the URL in a new tab, URL without scheme,
and state: found, fetched, cached (for a fork), the failure reason, not
fetched (cancelled run), or for files the size; plus "N kept" once
passages are selected. The Sources summary SHALL read "N of M fetched · K
files" and a danger note "N failed · run continues" SHALL show while any
page failed.

#### Scenario: Failed page
- **WHEN** `page.failed` arrives with reason "403 Forbidden"
- **THEN** that row shows "403 Forbidden" in the danger color and the header shows "1 failed · run continues"

### Requirement: Passages panel
The Live run screen (scenario `live`) SHALL show scored passages, best
first, each with its display score (two decimals), a 0 to 1 bar, a 1px
marker at the scorer's display threshold for that passage's query (title
"threshold <value>"), the domain or file path, the heading path joined by
" › ", the text clamped to three lines, and a badge: "above threshold"
before selection, the citation label once selected. The "Rejected" toggle
(also the R key outside text fields) SHALL show rejected passages at half
opacity with "rejected · below <threshold>"; rejected passages come from
the run's `scores.jsonl` and `chunks.jsonl` artifacts once the score stage
is done, with display scores mapped as the server maps kept ones (`jev`
divided by 3, `rerank` clamped to 0 to 1, `bm25` divided by the best score
of the same query). Passages from the `passthrough` fallback have no score:
they SHALL show "–" and no bar. The summary SHALL read "S/T
scored" while scoring and "K kept of T scored" after selection. Empty
states SHALL use the prototype's texts (waiting for the run, scorer waiting
for the GPU, cancelled before scoring, nothing above the threshold).

#### Scenario: Toggle rejected
- **WHEN** scoring is done and the user presses R
- **THEN** rejected passages appear at half opacity with their scores below the threshold marker

#### Scenario: Threshold from the scorer
- **WHEN** the scorer's display threshold for a query is 0.5
- **THEN** the marker of that query's passages sits at 50% of the bar

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
While the connection is opening, and after `run.queued` until `run.started`,
the Live run screen SHALL show the prototype scenario `loading`: tag
Connecting, the banner "Connecting to <ws origin>…" (with " · queued,
waiting for a free worker…" when queued), six shimmering skeleton rows in
Sources, "Waiting for the planner…" in Sub-queries, "Waiting for the run to
start." in Passages, and every phase pending.

#### Scenario: Queued
- **WHEN** `run.queued` is the last applied event
- **THEN** the banner says the run is queued and waiting for a free worker

### Requirement: Reconnecting state
When the event connection drops during a run, the Live run screen SHALL
show the prototype scenario `reconnecting` as a banner, never a modal: warn
"Connection lost. Reconnecting (attempt N)… The run continues on the
server; events replay from seq <n>.", then "Reconnected. Replaying N missed
events…", then "Reconnected · replayed N events, nothing lost." for 4.5
seconds. The screen SHALL stay usable and the footer SHALL show the
matching connection state.

#### Scenario: Recovery
- **WHEN** the connection drops at seq 351 and the second attempt succeeds and replays 54 events
- **THEN** the banner shows attempt 1, then attempt 2, then "Replaying 54 missed events", then "replayed 54 events, nothing lost", and disappears after 4.5 seconds

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

### Requirement: Report screen
The Report screen SHALL match the prototype scenario `finished`: Completed
tag, run id, meta `date · duration · recipe · N sources · N passages`, the
query as H1, the actions Rewrite, Copy markdown, Download .md, and Copy JSON
(context), the line "Written with <tone> · <words> words · <language> ·
<marker> [· custom instructions]", the report (headings, lists, citation
chips), and an aside with Sources (count fetched and failed, "N kept", the
citation labels that use each source) and Selected passages (label, score,
heading path, text, domain). A run with recipe `context` SHALL show the
selected passages in place of the report and SHALL NOT offer Rewrite or
Copy markdown or Download.

#### Scenario: Finished report
- **WHEN** the user opens a completed report run
- **THEN** the report, the sources with kept counts, and the selected passages are shown

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

### Requirement: Export
On the Report screen (scenario `finished`), "Copy markdown" SHALL copy the
report, "Download .md" SHALL save `<run id>.md` with `# <query>` and a
blank line before the report, and "Copy JSON (context)" SHALL copy
`{run, parent, query, options: {recipe, sources, profile, writing},
passages: [{cite, score, source, heading_path, text}]}`. Each SHALL confirm
with a toast ("Markdown copied", "Downloaded <id>.md", "Context JSON
copied").

#### Scenario: Download
- **WHEN** the user presses "Download .md" on run `r_8c21`
- **THEN** a file `r_8c21.md` starting with `# <query>` is saved and the toast "Downloaded r_8c21.md" shows

### Requirement: Rewrite
Rewrite on the Report screen (scenarios `finished` and `versions`) SHALL
open the prototype's "Rewrite report" dialog, prefilled with the viewed
version's writing options, marking each changed field "changed" with "was
<value>" and Reset, explaining that sources and passages are reused, and
showing "Creates v<N> linked to <id>". "Rewrite from write stage" SHALL
send `POST /api/runs/{id}/fork` with `from` = `write` and the changed
writing options, then show the new run on the Live run screen (Report tab on
phone) with reused phases, cached sources, the parent's passages, and the
banner "Rewrite of <id>: sources and passages are reused, only the write
stage runs." until writing starts. Cancel, the close button, Escape, and a
backdrop click SHALL close the dialog without a request.

#### Scenario: Rewrite shorter
- **WHEN** the user sets the length to 250 and confirms
- **THEN** a fork from `write` with `words` 250 is created and shown live with Plan to Select marked reused

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

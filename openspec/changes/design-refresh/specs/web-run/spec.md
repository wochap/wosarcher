# Spec Delta

## MODIFIED Requirements

### Requirement: Run options
The New run screen (scenario `new`) SHALL show the collapsible "Options"
panel, collapsed by default, whose header shows a summary of every value:
"<recipe> · <sources> · <profile> · <Tone> · <N> words · <Language> ·
<citation marker label> · <reference style>". The Run group SHALL offer
Recipe (segmented, `report` then `context`), Sources (segmented, `web`,
`files`, `both`), and Profile: a select `min(260px, 100%)` wide listing
the profiles from `GET /api/profiles` by name, a profile whose `source` is
`user` followed by "  (user profile)", the active one preselected, with the
selected profile's `description` under the select (12px, muted, 4px
above) when it is not empty. Each Run label sits at the top of its row in
the prototype's form grid. Recipe `context` SHALL start the run with
`until` set to `select`, so no report is written.

#### Scenario: Context recipe
- **WHEN** the user picks Recipe `context` and starts a run
- **THEN** the run request has `until` = `select`

#### Scenario: Profile description
- **WHEN** `GET /api/profiles` returns `low-vram` with the description "Models take turns on one small GPU; slower, fits 8 GB." and the user selects it (prototype `help` scenario, figure C)
- **THEN** the select shows `low-vram` and the description is shown under it

#### Scenario: User profile marked
- **WHEN** `GET /api/profiles` returns a profile `nixos` with `source` `user`
- **THEN** its option reads "nixos  (user profile)" and selecting it sends `profile` = `nixos`

### Requirement: Writing overrides
The Writing group of the Options panel (scenario `new`) SHALL use the
writing fields, labels, and controls of the Settings "Writing defaults"
panel and start from the saved writing defaults. A field whose value
differs from its default SHALL show the "overridden" mark followed by its
help button, "default: <value>", and a Reset button; a custom instruction
longer than 28 characters SHALL read as its first 28 characters followed
by "…" in that text. The panel header SHALL show "N overridden" and the
group SHALL offer "Reset all to defaults" while any field is overridden,
and an "edit defaults" link to Settings. When a default changes in
Settings, the New run value of that field SHALL follow it unless it is
overridden. The run request SHALL carry only the overridden writing
fields.

#### Scenario: One override
- **WHEN** the default length is 1200 and the user sets 600
- **THEN** Length (words) shows "overridden" and "default: 1200 words", the header shows "1 overridden", and the request sends `words` 600 and no other writing field

#### Scenario: Default follows Settings
- **WHEN** the tone is not overridden and the user changes the default tone in Settings
- **THEN** the New run tone shows the new default without an "overridden" mark

#### Scenario: Long custom instructions as default
- **WHEN** the default custom instructions are "Assume the reader knows CUDA well." and the user clears them for this run
- **THEN** the field shows "default: “Assume the reader knows CUDA w…”"

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

### Requirement: Phase timeline
The Live run screen (scenario `live`) SHALL show the nine phases Plan,
Search, Fetch, Load, Chunk, Prefilter, Score, Select, and Write as the
prototype's cards, each with icon, the full label (never truncated)
followed by the phase's help button, progress text, and a 3px progress
bar, styled per state: pending, waiting (warn dashed border, stripes, CPU
icon, text "waiting for GPU · <reason>"), running (accent, spinning icon,
glow), done, reused ("reused from <parent id>"), failed (danger, with the
error), and cancelled. Cards SHALL have no title tooltip. On desktop each
card SHALL be at least 98px wide and the row SHALL scroll sideways when
the nine cards do not fit; on phone the cards use two columns. Waiting
SHALL never look like running. Phases that a run's recipe skips SHALL show
done with "skipped".

#### Scenario: Waiting for a device
- **WHEN** the score stage has `resource.waiting` with released stage `prefilter` and has not started
- **THEN** the Score card shows the waiting style and "waiting for GPU · prefilter unloading"

#### Scenario: Narrow desktop window
- **WHEN** the Live run screen is 900px wide
- **THEN** every phase label is shown in full and the phase row scrolls sideways

### Requirement: Passages panel
The Live run screen (scenario `live`) SHALL show scored passages, best
first, each with its display score (two decimals), a 0 to 1 bar, a 1px
marker at the scorer's display threshold for that passage's query (title
"threshold <value>"), the domain or file path, the heading path joined by
" › ", the text clamped to three lines, and a badge: "above threshold"
before selection, the citation label once selected. The header SHALL wrap
when narrow and show, after "Passages", a neutral mono tag with the scorer
that produced the scores (the first query's scorer other than
`passthrough`, else `passthrough`), reading "<scorer> · fallback" when it
is not the run's configured `score.provider`, followed by the scorer help
button; then the summary followed by the score help button; then the
"Rejected" toggle followed by its help button. The "Rejected" toggle
(also the R key outside text fields) SHALL show rejected passages at half
opacity with "rejected · below <threshold>"; rejected passages come from
the run's `scores.jsonl` and `chunks.jsonl` artifacts once the score stage
is done, with display scores mapped as the server maps kept ones (`jev`
divided by 3, `rerank` clamped to 0 to 1, `bm25` divided by the best score
of the same query). Passages from the `passthrough` fallback have no score:
they SHALL show "–" and no bar. The summary SHALL read "S/T scored" while
scoring and "K kept of T scored" after selection, followed by " · ≥
<threshold>" (two decimals) when every scored query has the same display
threshold. Empty states SHALL use the prototype's texts (waiting for the
run, scorer waiting for the GPU, cancelled before scoring, nothing above
the threshold).

#### Scenario: Toggle rejected
- **WHEN** scoring is done and the user presses R
- **THEN** rejected passages appear at half opacity with their scores below the threshold marker

#### Scenario: Threshold from the scorer
- **WHEN** the scorer's display threshold for a query is 0.5
- **THEN** the marker of that query's passages sits at 50% of the bar

#### Scenario: Scorer tag and threshold in the summary
- **WHEN** the run's configured scorer is `jev`, every query was scored by `jev` with display threshold 0.6, and selection kept 14 of 96
- **THEN** the header shows the tag "jev" and "14 kept of 96 scored · ≥ 0.60"

#### Scenario: Fallback scorer
- **WHEN** the configured scorer is `rerank` and the passages were scored by `bm25`
- **THEN** the tag reads "bm25 · fallback"

### Requirement: Report screen
The Report screen SHALL match the prototype scenario `finished`: Completed
tag, run id, meta `date · duration · recipe · N sources · N passages`, the
query as H1, the actions Rewrite (followed by its help button), Copy
markdown, Download .md, and Copy JSON (context), the line "Written with
<Tone> · <N> words · <Language> · <citation marker label> · <reference
style> [· custom instructions]", the report (headings, lists, citation
chips), then the heading "References" (19px) followed by the reference
style name (12px, muted) and the reference style help button, with the
report's reference entries below it, and an aside with Sources (count
fetched and failed, "N kept", the citation labels that use each source)
and Selected passages (label, score, heading path, text, domain). A run
with recipe `context` SHALL show the selected passages in place of the
report and SHALL NOT offer Rewrite or Copy markdown or Download.

#### Scenario: Finished report
- **WHEN** the user opens a completed report run
- **THEN** the report, the sources with kept counts, and the selected passages are shown

#### Scenario: References heading
- **WHEN** the run's reference style is `MLA`
- **THEN** the heading reads "References" followed by "MLA" and a help button, and the "Written with" line ends with "· MLA"

## ADDED Requirements

### Requirement: Run help placements
The run screens SHALL place help buttons (web-shell "Inline help") where
the prototype places them, with these titles and bodies verbatim (the
accessible label is "Help: <label>"):

| Placement | Label | Title | Body | Example |
|---|---|---|---|---|
| New run, after "Attachments" | Attachments | Attachments | Markdown or text files to research alongside the web, or instead of it. | pdf-ingest output (.md) |
| Options, after "Recipe" | Recipe | Recipe | Report writes a cited report. Context stops after selecting passages and returns them with sources and scores, for agents or your own answer. Faster and cheaper. | |
| Options, after "Sources" | Sources | Sources | Web searches the internet. Files uses only your attachments. Both combines them; attachments get a share of the context budget. | |
| Options, after "Profile" | Profile | Profile | A named set of providers (search, fetch, embeddings, scorer, LLM) and GPU behavior. The list comes from the server. | |
| Options, after an "overridden" mark | Overridden | Overridden | This value differs from your default in Settings and applies to this run only. | |
| Rewrite dialog, after a "changed" mark | Changed | Changed | This value differs from the version you are rewriting. | |
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
| Passages header, after the summary | Score and threshold | Score and threshold | Each passage scores from 0 to 1. Passages right of the line are kept; the line is the scorer's configured threshold. | |
| Passages header, after the Rejected toggle | Rejected passages | Rejected passages | Shows passages that scored below the threshold or did not fit the budget. | |
| Failure card, after "Retry from Score" | Retry from Score | Retry from Score | Reruns scoring, selection and writing on the saved pages. Useful after changing the scorer or profile. | |
| Live footer, after the cost | Tokens and cost | Tokens and cost | Prompt and completion tokens across all stages. Cost is $0 for local models. | |
| Report, after Rewrite | Rewrite | Rewrite | Writes a new version from the same passages with different writing options. No new search; it creates a linked version. | |
| Report, after "Versions" | Versions | Versions | Reports that share the same research. v1 is the original; rewrites follow. | |
| Report, after the References style | Reference style | Reference style | Format of the reference list at the end of the report: APA, MLA, Chicago or IEEE. | |

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

#### Scenario: Rewrite mark help
- **WHEN** a field in the Rewrite dialog shows "changed" and the user taps the help button after it
- **THEN** the tooltip reads "Changed" and "This value differs from the version you are rewriting."

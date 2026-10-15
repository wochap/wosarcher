# web-catalog Specification

## Purpose

The web UI for catalog runs: the kind switch and catalog form on New run,
the catalog Live run variant, and the Catalog result screen.

## Requirements

### Requirement: Kind switch
The New run screen SHALL start with the prototype's Kind segmented
control (scenario `new`): "Research" (magnifying-glass icon) and
"Catalog" (tree-structure icon), Research selected by default, followed
by a help button with the prototype's `kind` entry ("Kind": "Research
answers a question: it plans searches, scores passages and writes a cited
report or answer. Catalog builds a table: it crawls out from seed
records, extracts one structured record per node and returns them as
JSON, a table and a graph. Pick Research for “what, why, compare”; pick
Catalog for “every X with its Y”."). Each segment SHALL carry the
prototype's title: "Cited report or answer to a question" for Research
and "Structured records, one per entity, from a crawl" for Catalog. The
`kind` entry SHALL appear on the Help spec page's New run group before
`recipe`. With Research selected the screen SHALL be the research form
(web-run "New run form"). With Catalog selected it SHALL show the catalog
form (Requirement: Catalog form). The chosen kind, the catalog form's
values, and the profile choice with its Advanced edits SHALL be kept with
the New run draft while the user moves between screens and cleared with
it after a run starts; the profile choice and edits are shared by both
kinds.

#### Scenario: Pick Catalog
- **WHEN** the user picks Catalog
- **THEN** the question textarea shows the catalog placeholder, the Options panel is hidden, and the "Draft structure" and "Run catalog" buttons are shown

#### Scenario: Kind kept across screens
- **WHEN** the user picks Catalog, types a brief, opens History, and returns to New run
- **THEN** Catalog is still selected with the brief

#### Scenario: Kind help
- **WHEN** the user hovers the help button after the Kind control
- **THEN** the popover shows the `kind` text

#### Scenario: Profile shared across kinds
- **WHEN** the user picks profile `cloud` and sets the model in Advanced on the research form, then picks Catalog
- **THEN** the catalog form's Profile row shows `cloud` with "1 edit" and the same model

### Requirement: Catalog form
With Catalog selected, the New run screen SHALL match the prototype
(scenario `new`, Catalog picked): the brief textarea (placeholder from the
prototype), the Attachments zone, the "Draft structure" secondary button
(sparkle icon; "Drafting…" with a spinning icon while the draft request
runs; disabled while the brief is blank), and the primary "Run catalog"
button, disabled until a structure exists. Draft structure SHALL post the
brief, the attachments, the profile, and the profile edits (`use` and
`llm`, with `reasoning.draft` when set) to `POST /api/catalog/draft` and
fill the Structure panel from the reply; a 502 SHALL show the error box
of web-run "Start a run" with the title "Couldn’t draft the structure".

The Structure panel SHALL show the heading "Structure", the line "Drafted
from your brief · edit anything", and these rows with the prototype's
help texts (`c-fields`, `c-vol`, `c-rel`, `c-seeds`, `c-leaf`, `c-expand`,
`c-output`, `c-limits`, `profile`, `c-lang`):
- Record fields: one row per field with the name input (spaces become
  `_`), the type select (`text`, `slug`, `url`, `date`, `enum`, `ref`),
  the Required and Volatile switches, and a remove button; an "Add
  field" link;
- Child relation: a single-line input;
- Seeds: chips with name, type, and a link icon when a URL is set, each
  removable; "Add seed" opens the inline name, type, and URL inputs
  (Enter adds, Escape cancels);
- Leaf types: toggle chips, one per enum value;
- Expand by: segmented Links, Search, Both;
- Output: segmented Table, Report, Both, from the structure's `output`;
- Limits: Max depth (1 to 10), Max nodes (1 to 5000), Pages per node (1
  to 10);
- Profile: the research form's Profile row (web-run "Run options") with
  its description line, the "based on <profile> · N edit(s)" line, and
  the Advanced toggle and box (web-run "Profile advanced values"), bound
  to the same choice and edits as the research form. In catalog mode the
  Advanced box's LLM group SHALL show "Draft thinking" (help
  `p-think-draft`) and "Extract thinking" (help `p-think-extract`) in
  place of the Plan, Gap, and Write thinking fields, bound to
  `llm.reasoning.draft` and `llm.reasoning.extract`; the other groups are
  unchanged;
- Allow domains, Block domains, and Search language, as web-run "Domain
  rows" and "Run options" define them;
- the estimate line "Up to <nodes> nodes · about <nodes × pages> pages ·
  <nodes> extraction calls", with " · 1 report" appended when Output is
  Report or Both.

When Output is Report or Both, a "Writing" panel SHALL follow the
Structure panel with the research form's Writing group (web-run "Writing
overrides"): the six fields, the "Preselected from your defaults" line
with the "edit defaults" link, and "Reset all to defaults"; Length
defaults to the saved writing default. The overridden fields SHALL be sent
as `writing`. With Output Table the panel is hidden and no `writing` is
sent.

Run catalog SHALL post `POST /api/runs` with `kind` `catalog`, the brief
as `query`, the structure (with `output`), the profile and its edits
(`use`, `llm` with `model`, `context_window`, `max_output_tokens`, and
`reasoning.draft` and `reasoning.extract` when set), the overridden
writing fields when Output is not Table, the domain lists, the search
language, and the attachments, then show the Live run screen. A
structure the server rejects SHALL show the error box with "Fix in
Structure", which focuses the named row. Ctrl+Enter in the brief SHALL
run the catalog when a structure exists.

#### Scenario: Draft fills the panel
- **WHEN** the user types a brief and presses Draft structure, and the server returns a structure with 12 fields and 6 seeds
- **THEN** the Structure panel shows those fields and seeds, the estimate reads "Up to 200 nodes · about 400 pages · 200 extraction calls", and Run catalog is enabled

#### Scenario: Edit a limit
- **WHEN** the user sets Max nodes to 50
- **THEN** the estimate reads "Up to 50 nodes · about 100 pages · 50 extraction calls"

#### Scenario: Rejected structure
- **WHEN** the server answers 422 naming `structure.seeds`
- **THEN** the error box shows the message and "Fix in Structure", which focuses the Seeds row

#### Scenario: Extract thinking sent
- **WHEN** the user opens Advanced on the catalog form, sets Extract thinking to `low`, and runs the catalog
- **THEN** the request has `llm.reasoning.extract` `low` and no `plan`, `gap`, or `write` step

#### Scenario: Profile picked on the catalog form
- **WHEN** the user picks profile `workstation` in the catalog form's Profile row
- **THEN** the request has `profile` `workstation`, and the research form shows `workstation` when the user switches back

#### Scenario: Report output picked
- **WHEN** the user picks Output Report, sets Length to 800, and runs the catalog
- **THEN** the Writing panel is shown before the run, the estimate ends with " · 1 report", and the request has `structure.output` `report` and `writing.words` 800

#### Scenario: Table hides writing
- **WHEN** the drafted structure has `output` `table`
- **THEN** no Writing panel is shown and the request has no `writing`

### Requirement: Catalog live run
The Live run screen of a catalog run SHALL match scenario `live-catalog`:
the header and banner of web-run "Live run header" with the meta "catalog ·
<sources> · <profile>"; the 8-phase timeline Load, Draft, Expand, Search,
Fetch, Chunk, Extract, Assemble with help texts `cp-load` to
`cp-assemble`, the loop phases showing "wave <k>" while running and "<n>
waves" when done, and each phase's detail text from its events (Draft:
"<n> fields · <n> seeds"; Expand: "<n> nodes expanding"; Search: "<n>
queries"; Fetch: "<n> pages"; Chunk: "<n> chunks"; Extract: "<n> records";
Assemble: "after the last wave", then "<n> records · <n> flagged");
column 1 with the Frontier panel (help `c-frontier`) over Sources; column
2 with Records; column 3 with Coverage (help `c-coverage`); and the footer
"wave <k> · <n> nodes expanding · <n> extracted · <n> failed" (failed in
the warn colour, omitted when 0). When the run's `output` is `report` or
`both`, the timeline SHALL add a ninth phase Write after Assemble, using
the research timeline's Write card (web-run "Phase timeline"), and once
`write` starts, column 3 SHALL show the streaming report panel (web-run
"Streaming report panel") in place of Coverage, with a "Coverage" ghost
toggle to switch back; this is an addition to the prototype's
`live-catalog` scenario.

The Frontier SHALL be a tree from `node.found` and status changes: rows
indented 14px per depth, a status dot (discovered faint, expanding accent
ring pulsing, extracted accent, failed warn), the name, the acronym-like
short value when the structure has a second `text` field, a type chip,
and the child count; nodes with children collapse with a caret; the
header shows "<n> known". Records SHALL list extracted nodes newest
first from `node.extracted`: name, type chip, a field grid with null
values as "—" in the warn colour, a source link per filled value, and a
flags line in the warn colour. Coverage SHALL show Limits (Nodes
<n>/<max>, Depth <d>/<max>, Pages <n>/<max> as bars), Fill per field
(sorted ascending, bars warn below 50%), and Nodes by type. Phone mode
SHALL use the tabs Progress, Sources, Records, Coverage (the last named
Report once `write` starts). When the run ends, the action SHALL be "Open
catalog" for `output` `table` and `both`, and "Open report" for `report`.

#### Scenario: Node extracted
- **WHEN** `node.extracted` arrives for INEI with `website` null and the flag "head_name from a source dated 2025-10-02"
- **THEN** the Frontier shows INEI with the extracted dot, Records shows its card first with "—" for website in the warn colour and the flag line, and the Extract phase count rises by one

#### Scenario: Wave counter
- **WHEN** wave 3 is running
- **THEN** the loop phases show "wave 3" and the footer starts with "wave 3"

#### Scenario: Finished catalog
- **WHEN** `catalog.done` arrives with 5 waves, 118 records, and 12 flagged
- **THEN** every phase is done, the loop phases show "5 waves", Assemble reads "118 records · 12 flagged", and "Open catalog" is shown

#### Scenario: Report streams
- **WHEN** a catalog run with `output` `both` reaches `write`
- **THEN** the timeline shows a ninth phase Write running, column 3 streams the report, and the run ends with "Open catalog"

### Requirement: Catalog result screen
`#/catalog/<run id>` SHALL show the Catalog result screen of scenario
`catalog-result`, built from `catalog.json`: the Completed tag, the run
ID, the meta "<date> · <duration> · catalog · <n> nodes · <n> sources",
the H1 from the brief; the actions Download JSON (primary; the `records`
array as `catalog.json`), Copy JSON, Download CSV (one column per field
plus `flags`, built in the client), Expand more (help `cr-expand`), and
Re-extract (help `cr-reextract`); the view switch Table, Graph, JSON; and
the Summary aside with the stop note, Nodes by depth bars, and the three
worst-filled fields, each a button that sets the "missing field" filter.
For a run with `output` `both` (scenario `catalog-result-both`), the
actions SHALL add Copy markdown and Download .md, and the view switch
SHALL add Report after JSON: the Report view shows the Report screen's
article (the "Written with …" line, the report, the References heading
with the reference style and its help button, and the references built
from the cited records) with record citations (Requirement: Record
citations).

Table SHALL show one column per field in order plus Flags (a warn badge
with the count), the type as a chip, the ref field as the parent's name,
null values as "—" in the warn colour; the filter bar with a search input
(name, short value, id), type chips with counts, a "flagged only" toggle
with the flagged count, a "missing field" select, the count "<n> records"
or "<n> of <N>", and "Clear filters" with the empty state "No records
match". Graph SHALL draw the tree from the ref field as inline SVG, left
to right, nodes coloured by type with a legend, flagged nodes with a warn
ring, each node a button. JSON SHALL show the `records` array with line
numbers and the summary "<n> records · <n> lines". Selecting a row or a
graph node SHALL open the drawer (380px; full width on phone) with the
name, type, id, depth, a warn callout with the flags, every field with
its value and its source as a link ("— not found" for null, "— seed, no
parent" for a null ref), and the pages used; Escape closes it.

Expand more SHALL open a dialog with the three limits prefilled with the
run's, each at least the run's, and post `POST /api/runs/{id}/fork` with
`from` `expand` and `limits`; Re-extract SHALL open a dialog with the
Rewrite dialog's model field and one thinking field "Extract thinking"
(help `p-think-extract`), and post the fork with `from` `extract` and
`llm` holding `model` and `reasoning.extract` when set. Both SHALL show
the new run on the Live run screen.

#### Scenario: Filter by missing field
- **WHEN** the user presses "website" in the Summary's worst-filled list
- **THEN** the Table view shows only records with `website` null and the count reads "<n> of <N>"

#### Scenario: Drawer
- **WHEN** the user selects SUNAT in the Graph view
- **THEN** the drawer shows its fields with a source link per filled value and the two pages used

#### Scenario: Expand more
- **WHEN** the user opens Expand more, sets Max depth to 4, and confirms
- **THEN** `POST /api/runs/{id}/fork` is sent with `{"from": "expand", "limits": {"max_depth": 4, "max_nodes": 200, "pages_per_node": 2}}` and the Live run screen shows the fork

#### Scenario: Download CSV
- **WHEN** the user presses Download CSV for a catalog of 118 records and 12 fields
- **THEN** a file with a header of 13 columns and 118 rows is downloaded, values with commas, quotes, or newlines quoted

#### Scenario: Re-extract with a level
- **WHEN** the user opens Re-extract, picks the model `deepseek-v4-flash` and Extract thinking `medium`, and confirms
- **THEN** `POST /api/runs/{id}/fork` is sent with `{"from": "extract", "llm": {"model": "deepseek-v4-flash", "reasoning": {"extract": "medium"}}}`

#### Scenario: Report view
- **WHEN** the user opens a catalog run with `output` `both` and picks the Report view
- **THEN** the report is shown with its references, Copy markdown copies it, and a citation chip opens the record popover

### Requirement: Catalog report screen
A finished catalog run with `output` `report` SHALL open on the Report
screen (scenario `finished-catalog`): web-run "Report screen" with the
meta "<date> · <duration> · catalog · <n> nodes · <n> sources", one extra
header action "Records" (table icon) that shows the Catalog result screen
for the run, the "Written with …" line, the report, and the References
list built from the cited records' sources; the aside's Sources list
SHALL show the cited records and the Selected passages list SHALL be
empty. Rewrite SHALL NOT be offered. Citation chips SHALL open the record
popover (Requirement: Record citations). `#/runs/<id>` and
`#/catalog/<id>` of such a run SHALL both show this screen.

#### Scenario: Report-only catalog
- **WHEN** a catalog run with `output` `report` ends
- **THEN** the Report screen shows its report with the Records action, and pressing Records shows the catalog table

### Requirement: Record citations
In a catalog report (Report screen for `output` `report`, Report view for
`both`), hovering or focusing a citation chip SHALL show the popover of
the prototype with the record's name, type, id, and the field values the
passage holds, and an "Open record" button. Pressing the chip, Enter on
it, or "Open record" SHALL open the record's drawer on the Catalog result
screen (`#/catalog/<id>` with the record selected). The popover SHALL
close when the screen changes.

#### Scenario: Open a cited record
- **WHEN** the user presses the citation `[4]` whose passage carries record ID `sunat`
- **THEN** the Catalog result screen opens with SUNAT's drawer

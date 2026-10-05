# cli-run Specification

## Purpose

Gives people and agents commands to start a run, fork a finished run, and
list runs, with readable progress on a terminal and stable JSON for scripts.

## Requirements

### Requirement: Run command
`wosarcher run "<query>"` SHALL start a run and accept these options:
`--attach PATH` (repeatable; files, directories, globs), `--sources
files|web|both` (default `both`), `--until STAGE`, `--profile NAME`,
`--depth NAME`, `--set KEY=VALUE` (repeatable), `--tone`,
`--tone-instructions`, `--words`, `--language`, `--citation-marker`,
`--reference-style`, `--sub-queries N`, `--results-per-query N`,
`--max-pages N`, `--passages-per-query N`, `--context-tokens N|auto`,
`--gap-context-tokens N|auto`, `--rounds N`, `--allow-domain DOMAIN`
(repeatable), `--block-domain DOMAIN` (repeatable), `--run-id ID`, and
`--json`. Each writing flag SHALL act as
`--set write.<field>=<value>`. Each research flag SHALL act as `--set` on
its key:
- `--sub-queries`: `plan.max_sub_queries`
- `--results-per-query`: `search.max_results`
- `--max-pages`: `fetch.max_pages`
- `--passages-per-query`: `score.top_k`
- `--context-tokens`: `select.max_context_tokens` (a positive integer or
  `auto`)
- `--gap-context-tokens`: `research.gap_context_tokens` (a positive
  integer or `auto`)
- `--rounds`: `research.rounds`

The `--allow-domain` values together SHALL set `search.allow_domains`, and
the `--block-domain` values `search.block_domains`, replacing the
configured list for that run; a list whose flag is not given is left
unchanged.

Writing, research, and domain flags SHALL take precedence over `--set` for
the same field. The depth preset SHALL apply below all of them (depth-presets
"Preset expansion").

#### Scenario: Writing flag
- **WHEN** the user runs `wosarcher run "q" --tone critical --words 500`
- **THEN** the run's resolved writing options have tone `critical` and words 500, and `request.json` lists both overrides

#### Scenario: Files without attachments
- **WHEN** the user runs `wosarcher run "q" --sources files` with no `--attach`
- **THEN** the command fails before creating a run, with an error that `--sources files` needs `--attach`

#### Scenario: Unknown stage
- **WHEN** the user runs `wosarcher run "q" --until rank`
- **THEN** the command fails with an error listing the valid stage names

#### Scenario: Depth with a research flag
- **WHEN** the user runs `wosarcher run "q" --depth deep --max-pages 80`
- **THEN** the resolved `fetch.max_pages` is 80, `plan.max_sub_queries` is 6, and `request.json` records depth `deep` and the `fetch.max_pages` override

#### Scenario: Rounds flag
- **WHEN** the user runs `wosarcher run "q" --depth deep --rounds 2`
- **THEN** the resolved `research.rounds` is 2

#### Scenario: Auto context flag
- **WHEN** the user runs `wosarcher run "q" --profile p --context-tokens auto` and profile `p` sets `select.max_context_tokens = 12000`
- **THEN** the resolved `select.max_context_tokens` is `auto`

#### Scenario: Gap context flag
- **WHEN** the user runs `wosarcher run "q" --depth deep --gap-context-tokens auto`
- **THEN** the resolved `research.gap_context_tokens` is `auto` and `request.json` records that override

#### Scenario: Domain flags
- **WHEN** the profile sets `search.allow_domains = ["gob.pe"]` and the user runs `wosarcher run "q" --allow-domain sunat.gob.pe --allow-domain sbs.gob.pe --block-domain facebook.com`
- **THEN** the resolved `search.allow_domains` is `["sunat.gob.pe", "sbs.gob.pe"]`, `search.block_domains` is `["facebook.com"]`, and `request.json` records both overrides

#### Scenario: Invalid domain flag
- **WHEN** the user runs `wosarcher run "q" --allow-domain "https://gob.pe/x"`
- **THEN** the command fails with exit status 2 before creating a run, with an error that names `search.allow_domains` and the entry

### Requirement: Human output
On a terminal, `wosarcher run` SHALL show live progress per stage (state,
counters, device, provider) and, when the run ends, print the report as
Markdown, or a summary of the context when the run stopped at `select`.
When standard output is not a terminal and `--json` is not given, it SHALL
print the report Markdown without progress. Progress, diagnostics, and
errors SHALL go to standard error: the live progress view when standard
error is a terminal and `--json` is not given, otherwise one diagnostic
line per run and stage event (see run-lifecycle, Diagnostics on standard
error).

#### Scenario: Piped output
- **WHEN** the user runs `wosarcher run "q" > report.md`
- **THEN** `report.md` contains only the report Markdown

#### Scenario: Standard error piped
- **WHEN** the user runs `wosarcher run "q" 2> run.log`
- **THEN** `run.log` has one line per stage start and end, and no progress view escape codes

### Requirement: JSON output
With `--json`, `wosarcher run` and `wosarcher fork` SHALL print exactly one
JSON document to standard output when the run ends: run ID, status, run
directory, the selected context (passages with numbers, chunk IDs, sources,
heading paths, text, and scores) when the select stage finished, and the
report (Markdown and references) when the write stage finished. Its schema
SHALL be included in `wosarcher schema`.

#### Scenario: Cited context for agents
- **WHEN** an agent runs `wosarcher run "q" --until select --json`
- **THEN** standard output is one JSON document with `status` `done`, a `context` with numbered passages and their sources, and `report` null

#### Scenario: Failed run
- **WHEN** a run with `--json` fails in the fetch stage
- **THEN** standard output is one JSON document with `status` `failed` and the error, and the exit status is 1

### Requirement: Chosen run ID
With `--run-id ID`, `wosarcher run` and `wosarcher fork` SHALL create the
run under that ID, so a caller such as the server can know the ID before
the process starts. When `<runs_dir>/<ID>/` already exists the command
SHALL exit with 2 and change nothing.

#### Scenario: ID used
- **WHEN** the user runs `wosarcher run "q" --run-id 20260101-120000-abcdef`
- **THEN** the run directory is `<runs_dir>/20260101-120000-abcdef/`

#### Scenario: ID taken
- **WHEN** `<runs_dir>/20260101-120000-abcdef/` exists and the same `--run-id` is given
- **THEN** the command exits with 2 and the existing directory is unchanged

### Requirement: Exit status
`wosarcher run` and `wosarcher fork` SHALL exit with 0 when the run ends
with `run.done`, 1 when it ends with `run.failed`, 130 when it is
cancelled, and 2 for invalid arguments or configuration.

#### Scenario: Invalid override
- **WHEN** the user runs `wosarcher run "q" --set score.topk=3`
- **THEN** the command exits with 2 and creates no run directory

### Requirement: Fork command
`wosarcher fork <run_id> --from <stage>` SHALL accept `--set`, the writing
flags, `--until`, `--profile`, `--run-id`, and `--json`, create a forked
run as the run store defines, and run it to the end or to `--until`. With
`--profile NAME` the fork's settings SHALL be resolved from that profile
and the parent's overrides plus the new overrides, instead of the parent's
saved settings, and the fork SHALL record `NAME` as its profile.

#### Scenario: Change the tone
- **WHEN** the user runs `wosarcher fork <id> --from write --tone critical`
- **THEN** a new run with the next version of the parent's lineage is created and only the write stage runs

#### Scenario: Retry with another profile
- **WHEN** the user runs `wosarcher fork <id> --from score --profile cloud`
- **THEN** the fork's score block comes from the `cloud` profile and its record names profile `cloud`

### Requirement: Runs command
`wosarcher runs` SHALL list runs newest first with ID, creation time,
status (`done`, `failed`, `cancelled`, or `interrupted`), version, parent
run ID, and query. `--limit N` SHALL limit the list (default 20) and
`--json` SHALL print the list as a JSON array.

#### Scenario: Status from the log
- **WHEN** a run's last run event is `run.failed`
- **THEN** `wosarcher runs` shows its status as `failed`

#### Scenario: Interrupted run
- **WHEN** a run's log has `run.started` and no `run.done`, `run.failed`, or `run.cancelled`
- **THEN** `wosarcher runs` shows its status as `interrupted`

### Requirement: Logs command
`wosarcher logs <run-id> [--follow] [--profile NAME] [--set KEY=VALUE]`
SHALL print the run's logged events, one line each:
`<HH:MM:SS> <stage or -> <type> <summary>`, where the time is the event
time in local time and the summary is a short description of `data`
(newlines replaced by spaces, at most 160 characters). Lines of
`events.jsonl` that do not parse SHALL be skipped. With `--follow`, it
SHALL keep printing new events as they are logged, checking at least every
second, and exit with 0 after printing a terminal event (`run.done`,
`run.failed`, `run.cancelled`). An unknown run SHALL exit with 2 and an
error naming the run. The runs directory comes from the resolved
configuration, as for `wosarcher runs`.

#### Scenario: Finished run
- **WHEN** the user runs `wosarcher logs <id>` for a run that failed in fetch
- **THEN** each logged event is printed on one line in `seq` order, the last one is `run.failed` with stage `fetch` and the first line of the error, and the exit status is 0

#### Scenario: Follow a running run
- **WHEN** the user runs `wosarcher logs <id> --follow` while the run is in the score stage
- **THEN** the events so far are printed, then each new event as it is logged, and the command exits with 0 after `run.done`

#### Scenario: Unknown run
- **WHEN** the user runs `wosarcher logs does-not-exist`
- **THEN** the command exits with 2 and the error names `does-not-exist`

#### Scenario: Long data shortened
- **WHEN** a `page.failed` event has a 200-character reason
- **THEN** its printed line's summary is at most 160 characters

### Requirement: Round progress
The CLI progress view SHALL show a `gap` row for multi-round runs only. A
loop stage's row SHALL show "round <k>/<N>" while it runs, and the number
of rounds it ran when done. The gap row SHALL show the follow-up count
after each gap step. When research ends, the view SHALL print one line:
"research: <ran> of <planned> rounds · <stop reason>".

#### Scenario: Multi-round progress
- **WHEN** a three-round run is in round 2's fetch
- **THEN** the fetch row shows "round 2/3"

#### Scenario: Research line
- **WHEN** a deep run stops after round 2 with `no new sources`
- **THEN** the view prints "research: 2 of 3 rounds · no new sources"

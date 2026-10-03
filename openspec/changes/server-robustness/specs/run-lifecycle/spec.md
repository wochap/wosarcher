## MODIFIED Requirements

### Requirement: Per-item failures continue
A failure of one item inside a stage (one search, one page, one scorer
batch) SHALL be logged and SHALL NOT stop the stage. The `reason` of a
`page.failed` event SHALL be the first line of the error text, cut to at
most 200 characters (ending with `…` when cut); the full error text SHALL
be written to the run process's standard error as a warning naming the
URL.

#### Scenario: One page fails
- **WHEN** one of five fetched URLs fails
- **THEN** a `page.failed` event names the URL and reason, and the fetch stage finishes with four pages

#### Scenario: Long Firecrawl error
- **WHEN** Firecrawl answers a scrape with a 3000-character, multi-line error
- **THEN** the `page.failed` reason is at most 200 characters with no newline, and the run's standard error has the full error text with the URL

### Requirement: Cancellation
Cancelling the run task, or the process receiving SIGTERM or SIGINT, SHALL
cancel in-flight requests, release the current GPU stage's model when the
policy is `exclusive`, write `costs.json` with the usage so far, emit
`run.cancelled` naming the current stage, and exit with status 130.

#### Scenario: SIGTERM during fetch
- **WHEN** the process receives SIGTERM during the fetch stage
- **THEN** in-flight fetch requests are cancelled, `run.cancelled` with stage `fetch` is the last logged event, and the process exits with status 130

#### Scenario: Costs of a cancelled run
- **WHEN** a run is cancelled during `fetch` after the plan stage used 100 input tokens
- **THEN** `costs.json` exists and shows 100 input tokens for `plan` and in the total, and the run's summary has a `cost`

## ADDED Requirements

### Requirement: Diagnostics on standard error
When the live progress view is not shown (standard error is not a
terminal, or `--json` is given), a run process SHALL write one line to
standard error for each `run.started`, `stage.started`, `stage.done`,
`stage.failed`, `resource.waiting`, `resource.released`, `run.done`,
`run.failed`, and `run.cancelled` event, one warning line for each warning
in a `stage.done`, and the full text of each page failure. Lines SHALL use
the format of `wosarcher logs` prefixed with the level (`INFO` or
`WARNING`). When the progress view is shown, nothing else SHALL be written
to standard error while it runs.

#### Scenario: Server-started run
- **WHEN** a run started by the server (standard error is a pipe) finishes the fetch stage with 12 pages and one warning
- **THEN** its standard error has an `INFO` line for `stage.done` of `fetch` with count 12, and a `WARNING` line with the warning text

#### Scenario: Terminal run
- **WHEN** a user runs `wosarcher run "q"` on a terminal and a page fails
- **THEN** the progress view is shown and no diagnostic line is written below it

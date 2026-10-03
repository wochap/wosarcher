## MODIFIED Requirements

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

## ADDED Requirements

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

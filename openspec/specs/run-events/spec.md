# run-events Specification

## Purpose

Defines the events a run emits, their order and storage, and how a client
that reconnects catches up, so the CLI, the server, and the frontend share
one event stream.

## Requirements

### Requirement: Event envelope
Every event SHALL have the fields `seq` (integer), `run_id`, `ts` (UTC ISO
8601 time), `type`, `stage` (absent when the event is not about a stage),
and `data` (an object whose shape is fixed by `type`).

#### Scenario: Envelope fields
- **WHEN** any event is read from `events.jsonl`
- **THEN** it has `seq`, `run_id`, `ts`, `type`, and `data`, and parses as the event type named by `type`

### Requirement: Event types
The system SHALL define exactly these event types and data:

| Type | Data |
|---|---|
| `run.queued` | position |
| `run.started` | query, profile, parent run ID, version, until |
| `run.done` | until, totals |
| `run.failed` | stage, error |
| `run.cancelled` | stage |
| `stage.started` | device, provider |
| `stage.progress` | done, total, failed |
| `stage.done` | count, seconds, usage and cost, provider that ran, skipped, copied from, warnings |
| `stage.failed` | error, next fallback (empty when none) |
| `resource.waiting` | device, released stage |
| `resource.released` | device, released stage |
| `plan.ready` | sub-queries |
| `hit.found` | URL, title, query IDs |
| `page.fetched` | URL, source ID, title, characters, cached |
| `page.failed` | URL, reason |
| `passages.scored` | query ID, scorer, pair count, kept count, display threshold, kept passages |
| `report.delta` | text |
| `report.snapshot` | text |

Each kept passage in `passages.scored` SHALL carry chunk ID, source ID,
source title and URI, heading path, text, and the display score from 0 to
1 that the score stage computed (`jev` divided by 3, `bm25` relative to the
best of the same query, others clamped), and the event SHALL carry the
stage's display threshold.

#### Scenario: Unknown type rejected
- **WHEN** an event with type `stage.paused` is parsed
- **THEN** parsing fails

#### Scenario: Display score for Jev
- **WHEN** Jev scores a kept passage 2.4 with `score.min_score = 1.5`
- **THEN** its display score is 0.8 and the display threshold is 0.5

### Requirement: Sequence and log
Appending an event to a run's `events.jsonl` SHALL assign `seq`: 1 for
the first event and the last logged `seq` plus 1 after that. The last
logged `seq` SHALL be read from the end of `events.jsonl` on every append,
so it is right also when another process or another store appended since
(for example the server after the run process exited). When the file ends
with a partial line, the appended event SHALL start on a new line and
follow the last complete event. The run SHALL append each event and only
then publish it to live listeners. Events SHALL be logged in the order
they happen.

Reading a log SHALL skip any line that does not parse as an event (a
partial last line, or a type from another version) instead of failing.

#### Scenario: Seq has no gaps
- **WHEN** a run finishes
- **THEN** the `seq` values in `events.jsonl` are 1, 2, 3, … with no gap or repeat

#### Scenario: Append after the run ended
- **WHEN** a run's log ends at `seq` 41 and another process appends `run.failed`
- **THEN** that event has `seq` 42

#### Scenario: Two stores take turns
- **WHEN** store A appends to a run, then store B appends to the same run, then store A appends again
- **THEN** the three events have `seq` 1, 2, and 3

#### Scenario: Append after a partial line
- **WHEN** `events.jsonl` holds complete events up to seq 9 followed by half a line, and an event is appended
- **THEN** the new event has seq 10, is on its own line, and reading the log returns events 1 to 10 without the partial line

#### Scenario: Log before publish
- **WHEN** a live listener receives a logged event
- **THEN** that event is already in `events.jsonl`

### Requirement: Live-only report deltas
`report.delta` events SHALL be published to live listeners and SHALL NOT be
written to `events.jsonl`. They SHALL carry the `seq` of the last logged
event. The streamed text SHALL be appended to `report.md` as it arrives.

#### Scenario: Deltas not logged
- **WHEN** the write stage streams 40 deltas
- **THEN** live listeners receive 40 `report.delta` events and `events.jsonl` contains none

### Requirement: Report snapshot
The system SHALL build a `report.snapshot` event from the current
`report.md` of a run, carrying the `seq` of the last logged event, so a
client that reconnects can replay logged events after its `seq` and then
receive the report text so far.

#### Scenario: Snapshot during write
- **WHEN** a snapshot is requested while the write stage has streamed "Intro"
- **THEN** the snapshot text is "Intro" and its `seq` equals the last logged `seq`

### Requirement: Event schema published
Every event type SHALL be a typed contract included in the output of
`wosarcher schema`.

#### Scenario: Schema covers events
- **WHEN** `wosarcher schema` runs
- **THEN** its output contains a definition for every event type in the table

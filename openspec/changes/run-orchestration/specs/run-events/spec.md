# Spec Delta

## Purpose

Defines the events a run emits, their order and storage, and how a client
that reconnects catches up, so the CLI, the server, and the frontend share
one event stream.

## ADDED Requirements

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
the first event and the last logged `seq` plus 1 after that, also when
another process (for example the server after the run process exited)
appends to a run that already has events. The run SHALL append each event
and only then publish it to live listeners. Events SHALL be logged in the order they happen.

#### Scenario: Seq has no gaps
- **WHEN** a run finishes
- **THEN** the `seq` values in `events.jsonl` are 1, 2, 3, … with no gap or repeat

#### Scenario: Append after the run ended
- **WHEN** a run's log ends at `seq` 41 and another process appends `run.failed`
- **THEN** that event has `seq` 42

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

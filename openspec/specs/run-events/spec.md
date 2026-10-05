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
| `stage.started` | device, provider, round |
| `stage.progress` | done, total, failed, round |
| `stage.done` | count, seconds, usage and cost, provider that ran, skipped, copied from, warnings, passthrough sub-query IDs, hits not fetched, hits filtered by domain, round |
| `stage.failed` | error, next fallback (empty when none) |
| `resource.waiting` | device, released stage |
| `resource.released` | device, released stage |
| `plan.ready` | sub-queries |
| `hit.found` | URL, title, query IDs |
| `page.fetched` | URL, source ID, title, characters, cached, round |
| `page.failed` | URL, reason |
| `passages.scored` | query ID, scorer, pair count, kept count, display threshold, kept passages |
| `round.done` | round, query IDs, new pages, known pages, kept passages |
| `gap.ready` | round it followed, follow-up queries (ID, text), note, uncovered query IDs, retried |
| `research.done` | planned rounds, rounds ran, stop reason, end note |
| `report.delta` | text |
| `report.snapshot` | text |

The `round` of stage and page events SHALL be the research round (1 for
single-round runs and for stages outside the loop). `round.done`,
`gap.ready`, and `research.done` SHALL be emitted only by multi-round runs.
`gap.ready` SHALL carry the stage `gap`. `round.done` SHALL carry `score`,
and `research.done` SHALL carry `gap`.

Each kept passage in `passages.scored` SHALL carry chunk ID, source ID,
source title and URI, heading path, text, and the display score from 0 to
1 that the score stage computed (`jev` divided by 3, `bm25` relative to the
best of the same query, others clamped), and the event SHALL carry the
stage's display threshold.

The `provider` of `stage.started` SHALL be the stage's configured provider
block as `<provider>:<model>`, or `<provider>` when the block has no model
(`built-in` for stages without a block). The `provider` of `stage.done`
SHALL name what actually ran in the same form. For the prefilter stage it is
`embeddings:<model>` when embeddings ran as configured, and `bm25` or `none`
otherwise. The `passthrough` list of `stage.done` SHALL hold the IDs of the
sub-queries whose pairs skipped ranking (small-input passthrough), in plan
order. Only the prefilter stage SHALL set it; it is empty for every other
stage. The `filtered` count of `stage.done` SHALL be the number of distinct
hits the domain filter dropped in that stage: the plan stage counts its
initial search, the search stage its own queries, and every other stage
reports 0.

#### Scenario: Unknown type rejected
- **WHEN** an event with type `stage.paused` is parsed
- **THEN** parsing fails

#### Scenario: Display score for Jev
- **WHEN** Jev scores a kept passage 2.4 with `score.min_score = 1.5`
- **THEN** its display score is 0.8 and the display threshold is 0.5

#### Scenario: Prefilter ran as configured
- **WHEN** the prefilter block is `provider = "embeddings"`, `model = "bge-small-en-v1.5"` and embeddings ranked every sub-query
- **THEN** `stage.started` and `stage.done` for prefilter both carry the provider `embeddings:bge-small-en-v1.5`

#### Scenario: Prefilter fell back
- **WHEN** the prefilter block is `provider = "embeddings"` and the embedder is unreachable
- **THEN** `stage.done` for prefilter carries the provider `bm25` and a warning naming the embedder failure

#### Scenario: Passthrough sub-queries
- **WHEN** the pages paired with `q4` and `q5` are shorter than `select.passthrough_chars`
- **THEN** `stage.done` for prefilter carries `passthrough` = `["q4", "q5"]`

#### Scenario: Round events
- **WHEN** a three-round run runs all its rounds
- **THEN** the log has `round.done` for rounds 1, 2, and 3, `gap.ready` after rounds 1 and 2 (each with its uncovered query IDs and `retried`), and one `research.done` with 3 planned, 3 ran, and reason `max rounds`

#### Scenario: Gap retry in events
- **WHEN** the gap step after round 1 gets no usable follow-up, asks again, and keeps two follow-ups
- **THEN** `gap.ready` for round 1 carries the two follow-ups and `retried` true

#### Scenario: Filtered hits counted
- **WHEN** `search.allow_domains = ["gob.pe"]` and the search stage drops 7 distinct hits from other domains
- **THEN** `stage.done` for search carries `filtered` = 7, and `stage.done` for fetch carries `filtered` = 0

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

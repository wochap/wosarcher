## MODIFIED Requirements

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

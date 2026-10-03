# event-streaming Specification

## Purpose

Streams a run's events to clients over a WebSocket so a browser can watch a
run live, lose its connection, and resume without missing or repeating a
logged event.

## Requirements

### Requirement: Event socket
`WS /api/runs/{id}/events?since=<seq>` SHALL send each event as one JSON text
message with the shape `{seq, run_id, ts, type, stage, data}`. `since`
SHALL default to 0. For an unknown run ID the server SHALL close the socket
with code 4404.

#### Scenario: Unknown run
- **WHEN** a client opens the event socket for a run ID that does not exist
- **THEN** the socket is closed with code 4404

### Requirement: Replay from a sequence number
On connect, the server SHALL first send every logged event of the run with
`seq` greater than `since`, in `seq` order. After the replay it SHALL send
new logged events as they are written, so the client receives each logged
event exactly once and in `seq` order, with no gap between replay and live
events.

#### Scenario: Reconnect after a drop
- **WHEN** a client that received events up to seq 351 reconnects with `since=351` while the run continues
- **THEN** it receives events 352 onward, each once, in order

#### Scenario: Event written during replay
- **WHEN** an event is written to the log while the server is replaying older events to a client
- **THEN** the client receives that event exactly once, after the replayed events

### Requirement: Report snapshot
After the replay, when the run's report text is not empty, the server SHALL
send one `report.snapshot` event whose `data.text` is the report text
written so far. The snapshot SHALL be sent on every connection, including
the first.

#### Scenario: Reconnect during writing
- **WHEN** a client reconnects while the write stage has produced 400 characters of report
- **THEN** after the replay it receives a `report.snapshot` with those 400 characters

### Requirement: Live report deltas
While a run started by this server is writing its report, the server SHALL
send `report.delta` events whose `data.text` is the report text appended
since the previous snapshot or delta sent to that client. When the report
text changes other than by appending (the final rendered report replaces
the streamed text), the server SHALL send a new `report.snapshot` instead
of a delta. The latest snapshot followed by all later deltas SHALL equal
the report text. `report.delta` and `report.snapshot` SHALL NOT be written
to `events.jsonl`.

#### Scenario: Deltas rebuild the report
- **WHEN** a client stays connected from before the write stage until the run ends
- **THEN** the text of its latest `report.snapshot` (empty if none) followed by every later `report.delta` equals the run's final `report.md`

#### Scenario: Final report rewritten
- **WHEN** the write stage ends and the final report differs from the streamed text
- **THEN** connected clients receive a `report.snapshot` with the final report text

### Requirement: Live-only event sequence numbers
Events that are not logged (`report.delta`, `report.snapshot`,
`run.queued`) SHALL carry the `seq` of the latest logged event sent to that
client before them, or 0 when none was sent, so a client that resumes from
the highest `seq` it saw never skips a logged event.

#### Scenario: Delta after event 40
- **WHEN** the last logged event a client received has seq 40 and a report delta follows
- **THEN** the delta has seq 40

### Requirement: Queued runs on the socket
While a run is queued, the server SHALL send a `run.queued` event with
`data.position` (1 for the next run to start) on connect and whenever the
position changes. When a queued run is cancelled, connected clients SHALL
receive a `run.cancelled` event before the socket closes.

#### Scenario: Position changes
- **WHEN** a client watches the second queued run and the running run finishes
- **THEN** the client receives `run.queued` with position 1

### Requirement: Stream end
After sending a terminal event (`run.done`, `run.failed`, or
`run.cancelled`), the server SHALL close the socket with code 1000. For a
run that is not queued and not running in this server (finished,
interrupted, or started by the CLI), the server SHALL replay, send the
snapshot, and close with code 1000.

#### Scenario: Finished run
- **WHEN** a client connects with `since=0` to a run with status `done`
- **THEN** it receives every logged event, then a `report.snapshot`, then the socket closes with code 1000

### Requirement: Slow clients
Each client SHALL have a bounded send buffer. When a client falls more than
1000 events behind, the server SHALL close its socket with code 4408 so it
reconnects with `since`, and other clients SHALL be unaffected.

#### Scenario: Stalled client
- **WHEN** one client stops reading while another keeps up
- **THEN** the stalled client's socket is closed with code 4408 and the other client still receives every event

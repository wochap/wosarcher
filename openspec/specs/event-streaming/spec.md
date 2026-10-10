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
with code 4404. The server SHALL decide whether the run is queued, running,
or ended after accepting the socket, so a run that ends while the socket
is being opened is treated as ended.

#### Scenario: Unknown run
- **WHEN** a client opens the event socket for a run ID that does not exist
- **THEN** the socket is closed with code 4404

#### Scenario: Run ends during the handshake
- **WHEN** a queued run is cancelled while a client's socket for it is being accepted
- **THEN** the client receives `run.cancelled` and the socket closes with 1000; it is never left open without events

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
While a run is writing its report, whichever process started it, the
server SHALL send `report.delta` events whose `data.text` is the report
text appended since the previous snapshot or delta sent to that client.
When the report text changes other than by appending (the final rendered
report replaces the streamed text), the server SHALL send a new
`report.snapshot` instead of a delta. The latest snapshot followed by all
later deltas SHALL equal the report text. `report.delta` and
`report.snapshot` SHALL NOT be written to `events.jsonl`.

#### Scenario: Deltas rebuild the report
- **WHEN** a client stays connected from before the write stage until the run ends
- **THEN** the text of its latest `report.snapshot` (empty if none) followed by every later `report.delta` equals the run's final `report.md`

#### Scenario: Final report rewritten
- **WHEN** the write stage ends and the final report differs from the streamed text
- **THEN** connected clients receive a `report.snapshot` with the final report text

#### Scenario: CLI run writing
- **WHEN** a client watches a `wosarcher run` started by an agent while its write stage streams
- **THEN** the client receives `report.delta` events that rebuild the run's `report.md`

### Requirement: Live-only event sequence numbers
Events that are not logged (`report.delta`, `report.snapshot`,
`run.queued`, and the `run.cancelled` or `run.failed` of a run that has no
run directory) SHALL carry the `seq` of the latest logged event sent to
that client before them, or 0 when none was sent, so a client that resumes
from the highest `seq` it saw never skips a logged event. Such a terminal
event therefore has a `seq` no greater than the client's last `seq`;
clients SHALL apply `run.done`, `run.failed`, and `run.cancelled`
whatever their `seq`.

#### Scenario: Delta after event 40
- **WHEN** the last logged event a client received has seq 40 and a report delta follows
- **THEN** the delta has seq 40

#### Scenario: Cancelled while queued
- **WHEN** a client watching a queued run with no logged events sees the run cancelled
- **THEN** it receives `run.cancelled` with seq 0, then the socket closes with 1000

### Requirement: Queued runs on the socket
While a run is queued, whichever process started it, the server SHALL send
a `run.queued` event on connect and whenever its data changes, with
`data.position` (1 for the next run to start), `data.limit` (the current
`max_concurrent_runs`), and `data.held` (the runs holding a slot, each
with `run_id`, `origin`, `token_name`, and `started`). When a queued run is
cancelled, connected clients SHALL receive a `run.cancelled` event before
the socket closes.

#### Scenario: Position changes
- **WHEN** a client watches the second queued run and the running run finishes
- **THEN** the client receives `run.queued` with position 1

#### Scenario: Slot holders
- **WHEN** a client watches a queued run while a web run and a CLI run hold the two slots
- **THEN** the `run.queued` event has `limit = 2` and two `held` entries with origins `web` and `cli`

### Requirement: Stream end
After sending a terminal event (`run.done`, `run.failed`, or
`run.cancelled`), the server SHALL close the socket with code 1000. For a
run that another process started and that is queued or running
(run-store "Status of a live run"), the server SHALL replay, then send new
logged events, queue updates, and report text as they appear, until the
run's terminal event; when that process exits without a terminal event,
the server SHALL close the socket with code 1000. For a run that is not
queued and not running (finished or interrupted), the server SHALL replay,
send the snapshot, and close with code 1000. For a run the server
remembers as ended without a run directory, it SHALL send that run's
terminal event and close with code 1000.

#### Scenario: Finished run
- **WHEN** a client connects with `since=0` to a run with status `done`
- **THEN** it receives every logged event, then a `report.snapshot`, then the socket closes with code 1000

#### Scenario: Run that failed before its directory existed
- **WHEN** a client connects to a run whose process exited before creating its run directory
- **THEN** it receives one `run.failed` event with seq 0 and the error text, then the socket closes with code 1000

#### Scenario: Follow a CLI run live
- **WHEN** a client connects to a CLI run in its `search` stage and the run continues to `run.done`
- **THEN** the client receives every later logged event as it is written, then `run.done`, then the socket closes with 1000

#### Scenario: CLI run killed while followed
- **WHEN** a client follows a CLI run and its process is killed with SIGKILL
- **THEN** the socket closes with 1000 within 2 seconds and the run's status is `interrupted`

### Requirement: Slow clients
Each client SHALL have a bounded send buffer. When a client falls more than
1000 events behind, the server SHALL close its socket with code 4408 so it
reconnects with `since`, and other clients SHALL be unaffected.

#### Scenario: Stalled client
- **WHEN** one client stops reading while another keeps up
- **THEN** the stalled client's socket is closed with code 4408 and the other client still receives every event

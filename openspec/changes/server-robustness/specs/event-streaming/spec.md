## MODIFIED Requirements

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

### Requirement: Stream end
After sending a terminal event (`run.done`, `run.failed`, or
`run.cancelled`), the server SHALL close the socket with code 1000. For a
run that is not queued and not running in this server (finished,
interrupted, or started by the CLI), the server SHALL replay, send the
snapshot, and close with code 1000. For a run the server remembers as
ended without a run directory, it SHALL send that run's terminal event and
close with code 1000.

#### Scenario: Finished run
- **WHEN** a client connects with `since=0` to a run with status `done`
- **THEN** it receives every logged event, then a `report.snapshot`, then the socket closes with code 1000

#### Scenario: Run that failed before its directory existed
- **WHEN** a client connects to a run whose process exited before creating its run directory
- **THEN** it receives one `run.failed` event with seq 0 and the error text, then the socket closes with code 1000

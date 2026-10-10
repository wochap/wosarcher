# run-queue Specification

## Purpose

Runs each server-started research run as its own `wosarcher run` or
`wosarcher fork` process, limits how many run at once so GPU stages are not
oversubscribed, and keeps the run log consistent when runs are cancelled or
their process dies.

## Requirements

### Requirement: One process per run
Each run started through the server SHALL execute as a separate
`wosarcher run` process (or `wosarcher fork` for forks) with the run ID
chosen by the server, so the CLI, the server, and the skill share one code
path. The server SHALL learn about the run only from its run directory
(`events.jsonl`, `report.md`) and the process exit code.

#### Scenario: Same artifacts as the CLI
- **WHEN** a run started through the server finishes
- **THEN** its run directory has the same artifacts a `wosarcher run` with the same request would produce

### Requirement: Concurrency limit
Runs started through the server SHALL wait for a slot in the shared run
queue (run-slots "One limit for every run"), so at most
`max_concurrent_runs` runs execute at a time, counting the runs other
processes started in the same runs directory. The server SHALL start a
queued run's process only once the run holds a slot, and the process SHALL
keep that slot until it exits. Further runs SHALL wait in first-in,
first-out order and start as soon as a slot frees.

#### Scenario: Second run waits
- **WHEN** `max_concurrent_runs = 1` and two runs are created one after the other
- **THEN** the second has status `queued` with position 1 until the first ends, and then starts

#### Scenario: Two slots
- **WHEN** `max_concurrent_runs = 2` and three runs are created
- **THEN** two run at once and the third is queued with position 1

#### Scenario: Queued behind a CLI run
- **WHEN** `max_concurrent_runs = 1`, a CLI run holds the slot, and a run is created through the API
- **THEN** the API run has status `queued` with position 1 and no process until the CLI run ends

### Requirement: Staged queued runs
A queued run's request and attachments SHALL be stored in a staging
directory inside the runs directory until its process starts. While it is
staged, the server SHALL hold its place in the shared run queue. When the
server starts, staged runs SHALL be queued again in creation order, behind
runs that were already waiting. The staging directory of a run SHALL be
removed when its process exits.

#### Scenario: Restart with a queue
- **WHEN** the server stops while two runs are queued and starts again
- **THEN** both runs are queued again in their original order

#### Scenario: Queue place lost while the server is down
- **WHEN** the server stops while a run is queued, a CLI run starts waiting, and the server starts again
- **THEN** the CLI run is ahead of the staged run in the queue

### Requirement: Cancel
`POST /api/runs/{id}/cancel` SHALL, for a running run whose process the
server started, send SIGTERM to its process and answer 202 with
`{"run_id", "result": "signalled"}`. When the process has not exited 10
seconds after SIGTERM, the server SHALL send SIGKILL and append
`run.cancelled` to the run's log. For a queued run the server staged it
SHALL remove the run from the queue, delete its staging directory, notify
connected clients with `run.cancelled`, and answer 200 with
`{"run_id", "result": "dequeued"}`. For a run another process started
(origin `cli`), waiting or running, it SHALL make a cancel request
(run-slots "Cancel request for a run in another process") and answer 202
with `{"run_id", "result": "signalled"}`; the run's own process writes
`run.cancelled`. For a known run in any other state (`done`, `failed`,
`cancelled`, or `interrupted`) it SHALL answer 409 with
`error = "run_not_active"`, a `detail`, the `run_id`, and the run's current
`status`. An unknown run SHALL answer 404 `run_not_found`.

#### Scenario: Cancel a running run
- **WHEN** a client cancels a running run whose process handles SIGTERM
- **THEN** the process exits, the log ends with `run.cancelled`, and the next queued run starts

#### Scenario: Process ignores SIGTERM
- **WHEN** a run's process does not exit within 10 seconds of SIGTERM
- **THEN** it is killed and the server appends `run.cancelled` to its log

#### Scenario: Cancel a running CLI run
- **WHEN** a client cancels a run that `wosarcher run` started and that is running
- **THEN** the response is 202 with `result = "signalled"`, the run's log ends with `run.cancelled`, and the CLI exits with 130

#### Scenario: Cancel a waiting CLI run
- **WHEN** a client cancels a CLI run that waits for a slot
- **THEN** the response is 202, the run's log ends with `run.cancelled`, and the run never starts its first stage

#### Scenario: Cancel a finished run
- **WHEN** a client cancels a run with status `done`
- **THEN** the response is 409 with `{"error": "run_not_active", "detail": ..., "run_id": <id>, "status": "done"}`

#### Scenario: Cancel a run that already failed
- **WHEN** a run's process failed and a client that still shows it running sends cancel
- **THEN** the response is 409 with `status = "failed"`

### Requirement: Process exit without a terminal event
When a run process exits and its log has no `run.done`, `run.failed`, or
`run.cancelled`, the server SHALL append `run.failed` with the exit code
and the last 20 lines of the process's standard error as the error text,
using the next `seq`. When the process was killed after a cancel, the
server SHALL append `run.cancelled` instead. When the log ends with a
partial line (the process was killed while writing), the appended event
SHALL start on a new line and carry the `seq` after the last complete
event.

#### Scenario: Crash
- **WHEN** a run process exits with code 1 after `stage.started` for `score`
- **THEN** the log ends with a `run.failed` event that includes exit code 1 and the error output

#### Scenario: Killed while writing an event
- **WHEN** a run process is killed while `events.jsonl` ends with half of a `passages.scored` line, and the last complete event has seq 17
- **THEN** the server appends `run.cancelled` with seq 18 on its own line, and the next queued run starts

### Requirement: Shutdown
When the server shuts down, it SHALL send SIGTERM to every running run
process and wait up to 10 seconds for them to exit. Queued runs SHALL stay
staged.

#### Scenario: Stop the server during a run
- **WHEN** the server is stopped while a run is running
- **THEN** the run process receives SIGTERM and its log ends with `run.cancelled`

### Requirement: Finishing a run never stalls the queue
Whatever goes wrong while the server watches or finishes a run process (an
unreadable event line, an event type it does not know, a standard-error
line of any length, a failed file write), the server SHALL still close the
run's event stream, remove its staging directory, free its slot, and start
the next queued run. The error SHALL be written to the server log.

#### Scenario: Unreadable event line
- **WHEN** a run process writes a line that is not a valid event to `events.jsonl`, then continues and ends with `run.done`
- **THEN** connected clients receive every valid event and `run.done`, the server log has a warning naming the run, and the next queued run starts

#### Scenario: Very long standard-error line
- **WHEN** a run process writes one 100 KB line to standard error and exits with code 1
- **THEN** the run's log ends with `run.failed` whose error includes the start of that line, and the next queued run starts

### Requirement: Run standard error in the server log
The server SHALL write each line a run process prints to standard error to
the server log at level `info`, prefixed with `run <run_id>: `. A line
longer than 4000 characters SHALL be cut to 4000 characters followed by
`…` in the log and in the last-20-lines tail. The last 20 lines SHALL still
be kept for the `run.failed` error text.

#### Scenario: Forwarded line
- **WHEN** run `20260101-120000-abcdef` prints `WARNING fetch https://x.test failed: HTTP 500` to standard error
- **THEN** the server log has a line containing `run 20260101-120000-abcdef: WARNING fetch https://x.test failed: HTTP 500`

### Requirement: Run lifecycle in the server log
The server SHALL write one log line, naming the run ID, when a run is
queued (with its position), when its process starts (with the command,
`run` or `fork`, and the process ID), and when it ends: `done` at level
`info`, `cancelled` at level `info` (also for a run removed from the queue),
and `failed` at level `warning` with the stage and the first line of the
error. A cancel request for a run another process started SHALL be logged
at level `info` with the run ID.

#### Scenario: Failed run logged
- **WHEN** a run fails in the `fetch` stage with the error `no output`
- **THEN** the server log has a warning line containing the run ID, `failed`, `fetch`, and `no output`

#### Scenario: Queued run logged
- **WHEN** a run is created while another runs and `max_concurrent_runs = 1`
- **THEN** the server log has a line containing its run ID, `queued`, and position 1

### Requirement: Runs that end without a run directory
When a queued run is cancelled, or a run process exits before creating its
run directory, the server SHALL remember the run with status `cancelled` or
`failed`, its terminal event, and its staged request until the server
restarts or the run is deleted (at most the 100 most recent such runs).
Such a run SHALL appear in `GET /api/runs` and `GET /api/runs/{id}` with
that status, and its event socket SHALL send its terminal event and close
with 1000.

#### Scenario: Cancelled while queued
- **WHEN** a queued run is cancelled and a client then requests `GET /api/runs/{id}`
- **THEN** the response is 200 with `status = "cancelled"` and `last_seq = 0`

#### Scenario: Process exits before the run directory exists
- **WHEN** a run process exits with code 2 and the error `error: unknown profile 'x'` before creating its run directory
- **THEN** `GET /api/runs/{id}` answers 200 with `status = "failed"` and an `error` containing `unknown profile 'x'`

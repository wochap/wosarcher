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
At most `server.max_concurrent_runs` (default 1) run processes SHALL be
running at a time. Further runs SHALL wait in first-in, first-out order and
start as soon as a slot frees.

#### Scenario: Second run waits
- **WHEN** `server.max_concurrent_runs = 1` and two runs are created one after the other
- **THEN** the second has status `queued` with position 1 until the first ends, and then starts

#### Scenario: Two slots
- **WHEN** `server.max_concurrent_runs = 2` and three runs are created
- **THEN** two run at once and the third is queued with position 1

### Requirement: Staged queued runs
A queued run's request and attachments SHALL be stored in a staging
directory inside the runs directory until its process starts. When the
server starts, staged runs SHALL be queued again in creation order. The
staging directory of a run SHALL be removed when its process exits.

#### Scenario: Restart with a queue
- **WHEN** the server stops while two runs are queued and starts again
- **THEN** both runs are queued again in their original order

### Requirement: Cancel
`POST /api/runs/{id}/cancel` SHALL, for a running run, send SIGTERM to its
process and answer 202. When the process has not exited 10 seconds after
SIGTERM, the server SHALL send SIGKILL and append `run.cancelled` to the
run's log. For a queued run it SHALL remove the run from the queue, delete
its staging directory, notify connected clients with `run.cancelled`, and
answer 200. For a run in any other state it SHALL answer 409.

#### Scenario: Cancel a running run
- **WHEN** a client cancels a running run whose process handles SIGTERM
- **THEN** the process exits, the log ends with `run.cancelled`, and the next queued run starts

#### Scenario: Process ignores SIGTERM
- **WHEN** a run's process does not exit within 10 seconds of SIGTERM
- **THEN** it is killed and the server appends `run.cancelled` to its log

#### Scenario: Cancel a finished run
- **WHEN** a client cancels a run with status `done`
- **THEN** the response is 409

### Requirement: Process exit without a terminal event
When a run process exits and its log has no `run.done`, `run.failed`, or
`run.cancelled`, the server SHALL append `run.failed` with the exit code
and the last 20 lines of the process's standard error as the error text,
using the next `seq`.

#### Scenario: Crash
- **WHEN** a run process exits with code 1 after `stage.started` for `score`
- **THEN** the log ends with a `run.failed` event that includes exit code 1 and the error output

### Requirement: Shutdown
When the server shuts down, it SHALL send SIGTERM to every running run
process and wait up to 10 seconds for them to exit. Queued runs SHALL stay
staged.

#### Scenario: Stop the server during a run
- **WHEN** the server is stopped while a run is running
- **THEN** the run process receives SIGTERM and its log ends with `run.cancelled`

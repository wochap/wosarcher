# run-slots Specification

## Purpose

Limits how many research runs execute at once on one machine, for every run
that shares a runs directory, whether the server or the CLI started it, and
keeps the waiting runs in one first-in, first-out queue.

## Requirements

### Requirement: One limit for every run
Every run that uses a runs directory SHALL count against one limit,
`max_concurrent_runs`, whether the server started it or a `wosarcher run`
or `wosarcher fork` command did. The limit SHALL be read from the global
settings file (`server-settings.json` in the wosarcher config directory)
each time a run asks for a slot. Allowed values SHALL be 1 to 8. When the
file does not exist, the limit SHALL be 1. When the file cannot be read or
does not hold valid settings, the limit SHALL be 1 and a warning naming the
file SHALL be logged. The rule SHALL hold whether or not a server is
running.

#### Scenario: CLI run waits behind a server run
- **WHEN** `max_concurrent_runs` is 1, a run started through the server is running, and an agent runs `wosarcher run "q"`
- **THEN** the CLI run waits and starts its first stage only after the server run has ended

#### Scenario: No settings file
- **WHEN** no `server-settings.json` exists and two `wosarcher run` commands start one after the other
- **THEN** the second waits until the first has ended

#### Scenario: Two slots
- **WHEN** `max_concurrent_runs` is 2 and three runs ask for a slot, one from the web UI and two from the CLI
- **THEN** two run at once and the third waits

#### Scenario: No server running
- **WHEN** the server is stopped, `max_concurrent_runs` is 1, and two CLI runs start
- **THEN** the second waits for the first

### Requirement: Slot held for the life of the run
A run SHALL hold its slot from before its first stage until its process
exits. A slot SHALL be freed when that process exits for any reason,
including a crash or SIGKILL, without help from any other process.

#### Scenario: Killed CLI run frees its slot
- **WHEN** a CLI run holding the only slot is killed with SIGKILL while another run waits
- **THEN** the waiting run takes the slot within 2 seconds

### Requirement: First in, first out
Waiting runs SHALL take free slots in the order they started waiting,
oldest first, whoever started them. A run whose waiting process has exited
SHALL lose its place and SHALL NOT block the runs behind it.

#### Scenario: Order across origins
- **WHEN** `max_concurrent_runs` is 1, a run is running, then a web run starts waiting, then a CLI run starts waiting
- **THEN** the web run starts when the running run ends, and the CLI run starts after the web run ends

#### Scenario: Waiting process gone
- **WHEN** a CLI run that waits first in line is killed, and the running run ends
- **THEN** the next waiting run takes the slot

### Requirement: Changing the limit
A new limit SHALL apply at the next slot decision, without a restart of the
server or of any waiting CLI command. Runs that hold a slot when the limit
is lowered SHALL keep running; new runs SHALL start only while fewer runs
than the new limit hold a slot.

#### Scenario: Raise the limit
- **WHEN** one run is running, one waits, and `max_concurrent_runs` is raised from 1 to 2
- **THEN** the waiting run starts within 2 seconds

#### Scenario: Lower the limit
- **WHEN** three runs are running with `max_concurrent_runs = 3`, one waits, and the limit is lowered to 1
- **THEN** the three runs continue, and the waiting run starts only after all three have ended

### Requirement: Slot state
The slot state SHALL be readable by any process that shares the runs
directory: the limit, each run that holds a slot (run ID, origin, token
name for API runs, start time), and each waiting run in queue order (run
ID, origin, token name). A slot or queue entry whose process has exited
SHALL NOT appear in the state.

#### Scenario: State lists holders
- **WHEN** a web run and a CLI run hold the two slots and one API run waits
- **THEN** the slot state lists both holders with origins `web` and `cli` and one waiting run with origin `api` and its token name

### Requirement: Cancel request for a run in another process
A process SHALL be able to ask for any live run in the same runs directory
to be cancelled, waiting or running, without signalling its process. The
run's own process SHALL notice the request within 1 second and cancel the
run as it does on SIGTERM: a running run ends with `run.cancelled`, and a
waiting run leaves the queue and ends with `run.cancelled` without
starting its first stage.

#### Scenario: Cancel a waiting CLI run
- **WHEN** a cancel request is made for a CLI run that waits for a slot
- **THEN** the CLI leaves the queue, the run's log ends with `run.cancelled`, and the command exits with 130

# daemon-command Specification

## Purpose

Defines the `wosarcherd` command: the server with its listeners, the engine
commands it spawns, the local admin commands, and the run lock that tells
every reader whether a run process is alive.

## Requirements

### Requirement: Daemon command
`wosarcherd` SHALL provide `serve`, `run`, `fork`, `doctor`, `auth
set-password`, and `profile use`. `run`, `fork`, and `doctor` SHALL behave
as the engine the server spawns: they resolve the configuration (secrets
included), execute in the current process, and write the run directory.
`wosarcherd run` and `wosarcherd fork` SHALL accept every option
`wosarcher run` and `wosarcher fork` accept except `--attach` paths are
read from disk by the daemon process, plus `--run-id ID`, and the hidden
`--origin` and `--token-name` the server passes. A run started by
`wosarcherd run` directly SHALL record origin `cli` and SHALL NOT be queued
or counted by a server's queue.

#### Scenario: Direct engine run
- **WHEN** a developer runs `wosarcherd run "q" --until load --json` with a profile in the environment
- **THEN** the run directory is written, standard output is one `RunOutput` document, and no server is involved

#### Scenario: Client has no engine flags
- **WHEN** the user runs `wosarcher run "q" --run-id 20260101-120000-abcdef`
- **THEN** the command exits with 2 naming the unknown option

### Requirement: Chosen run ID
With `--run-id ID`, `wosarcherd run` and `wosarcherd fork` SHALL create the
run under that ID, so the server can know the ID before the process
starts. When `<runs_dir>/<ID>/` already exists the command SHALL exit with
2 and change nothing.

#### Scenario: ID used
- **WHEN** the server spawns `wosarcherd run "q" --run-id 20260101-120000-abcdef`
- **THEN** the run directory is `<runs_dir>/20260101-120000-abcdef/`

#### Scenario: ID taken
- **WHEN** `<runs_dir>/20260101-120000-abcdef/` exists and the same `--run-id` is given
- **THEN** the command exits with 2 and the existing directory is unchanged

### Requirement: Run lock
A run process SHALL hold an exclusive lock on `<run>/.lock` from the
moment the run directory exists until the process exits, so the lock is
dropped by the kernel on any exit, including SIGKILL. Any reader of the
runs directory SHALL tell a live run process from a dead one by testing
that lock, without a registry of processes.

#### Scenario: Process killed
- **WHEN** a run process is killed with SIGKILL during the `score` stage
- **THEN** within 1 second the lock is free and the run's status is `interrupted`

#### Scenario: Lock survives a server restart
- **WHEN** the server restarts while a run process it spawned is in `fetch`
- **THEN** after the restart the run's status is `running`

### Requirement: Serve listeners
`wosarcherd serve` SHALL listen on TCP at `server.host` and `server.port`
(or `--host`, `--port`) and on a Unix socket: the listening descriptor
passed by systemd socket activation (`LISTEN_FDS`) when present, else the
path from `--socket PATH` or `server.socket`, whose default is
`$XDG_RUNTIME_DIR/wosarcher.sock` when `XDG_RUNTIME_DIR` is set and none
otherwise; `--no-socket` disables the socket listener. A socket the daemon
creates SHALL have mode 0660 and SHALL replace a stale socket file at that
path. Requests on the socket listener SHALL be authenticated with method
`socket` (admin-auth "Authentication mode"). Both listeners SHALL serve the
same application, routes, and event WebSocket.

#### Scenario: Socket created
- **WHEN** `wosarcherd serve --socket /tmp/w.sock` starts
- **THEN** `/tmp/w.sock` exists with mode 0660 and `GET /api/session` over it answers `method = "socket"`

#### Scenario: Inherited descriptor
- **WHEN** systemd starts `wosarcherd serve` with `LISTEN_FDS=1` for a Unix socket
- **THEN** the daemon serves the API on that socket and binds no other Unix socket

#### Scenario: No socket
- **WHEN** `wosarcherd serve --no-socket` runs with `XDG_RUNTIME_DIR` unset
- **THEN** only the TCP listener is open

### Requirement: Profile use
`wosarcherd profile use NAME` SHALL store `NAME` as the default profile in
the daemon's config directory, as `wosarcher profile use` did; an unknown
name SHALL exit with 2 listing the profiles.

#### Scenario: Default stored
- **WHEN** the service user runs `wosarcherd profile use cloud`
- **THEN** the next server-started run without a profile resolves `cloud`

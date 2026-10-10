# run-hooks Specification

## Purpose

Lets other programs react when a server run ends, through webhook POSTs or
local commands set up in one global hooks file that the API cannot reach.

## Requirements

### Requirement: Hooks file

Hooks SHALL be read only from `$XDG_CONFIG_HOME/wosarcher/hooks.toml` of
the server (`~/.config/wosarcher/hooks.toml` when `XDG_CONFIG_HOME` is
unset). A missing file SHALL mean no hooks. The file SHALL hold a list of
`[[on_finish]]` tables, each with exactly one of:

- `url`: an `http` or `https` URL, or
- `command`: a non-empty list of strings (program and arguments).

Each entry MAY also set:

- `status`: a non-empty list of `done`, `failed`, and `cancelled`.
  Default: all three.
- `timeout`: positive seconds. Default: 10.
- `headers` (only with `url`): a table of header names to values.
- At most one of `secret`, `secret_file`, or `secret_command` (only with
  `url`).

A header value SHALL be either a string, or a table with exactly one of
`value` (a string), `value_file` (a path), or `value_command` (an argv
list). A string is shorthand for `{ value = "..." }`. `secret_file`,
`value_file`, `secret_command`, and `value_command` SHALL follow the
secret-sources rules: a file's trailing newline is stripped; a command runs
without a shell or a terminal, must exit 0 within 10 seconds, and its
standard output (trailing newline stripped) is the value. A command SHALL
be non-interactive, since the server has no terminal.

Any other key, an entry with both or neither of `url` and `command`, more
than one secret source, a header table with zero or several sources, or a
wrong type SHALL make the file invalid, and the error SHALL name the file,
the entry's position, and the key.

Hooks SHALL NOT be settable through profiles, `WOSARCHER_*` environment
variables, `--set`, `RunCreate.set`, or `PUT /api/settings`. No API
endpoint SHALL read or write the hooks file.

#### Scenario: No hooks file

- **WHEN** `hooks.toml` does not exist and a server run ends
- **THEN** no hook fires and nothing is logged about hooks

#### Scenario: Entry with both url and command

- **WHEN** an `[[on_finish]]` entry sets both `url` and `command`
- **THEN** the file is invalid and the error names `hooks.toml`, the
  entry's position, and the conflicting keys

#### Scenario: Two secret sources

- **WHEN** an entry sets both `secret` and `secret_file`
- **THEN** the file is invalid and the error names both keys

#### Scenario: Empty header table

- **WHEN** an entry sets `headers = { Authorization = {} }`
- **THEN** the file is invalid and the error names the header

#### Scenario: Hook key through the API is rejected

- **WHEN** a run is created with `set = ["hooks.on_finish=..."]`
- **THEN** the request fails as for any other unknown settings key

### Requirement: Secrets resolve when a hook fires

The server SHALL read and validate `hooks.toml` and resolve each hook's
secret sources each time a run ends, not once at start. An edited file, a
rewritten file, or a rotated secret SHALL apply to the next run that ends,
without a restart. Resolving secrets SHALL NOT block the server from
serving other requests. A secret source that fails (unreadable file,
command that fails or times out) SHALL skip only that hook.

#### Scenario: Server re-reads the file

- **WHEN** `hooks.toml` is edited while the server is running
- **THEN** the next run that ends uses the edited file

#### Scenario: Rotated secret file

- **WHEN** the file named by `secret_file` changes between two run ends
- **THEN** the second webhook is signed with the new value

#### Scenario: Failing secret command skips one hook

- **WHEN** the first entry's `secret_command` exits 1 and a second entry is
  valid
- **THEN** the first hook does not fire, the failure is logged without the
  command's output, and the second hook fires

### Requirement: The server fires hooks at most once per run

When a run started by the server ends with `run.done`, `run.failed`, or
`run.cancelled`, each `[[on_finish]]` entry whose `status` includes the
run's status SHALL fire at most once, and never twice. Entries SHALL fire
one after another in file order. The server SHALL fire for:

- a terminal event the run process wrote;
- a `run.failed` the server recorded after the process crashed or failed
  to start;
- a `run.cancelled` the server recorded after it killed the process past
  the grace period;
- a cancel while the run was queued;
- a run cancelled because the server is shutting down.

The server SHALL fire only after the run's terminal event is recorded; if
recording it fails, no hook fires. A run with no terminal event
(interrupted), and a run process that outlives a server restart, SHALL NOT
fire hooks. `wosarcherd run`, `wosarcherd fork`, and the `wosarcher` client
SHALL never fire hooks.

#### Scenario: Done run fires once

- **WHEN** a server run ends with `run.done` and `hooks.toml` has one entry
  with no `status` filter
- **THEN** that hook fires once with status `done`

#### Scenario: Status filter

- **WHEN** a run ends with `run.done` and the only entry sets
  `status = ["failed"]`
- **THEN** no hook fires

#### Scenario: Crash is reported by the server

- **WHEN** a server run process exits with code 1 and leaves no terminal
  event
- **THEN** the server records `run.failed` and fires the hooks once with
  status `failed`

#### Scenario: Kill after the grace period

- **WHEN** a cancelled run ignores SIGTERM and is killed after the grace
  period
- **THEN** the hooks fire once with status `cancelled`

#### Scenario: Cancel while queued

- **WHEN** a queued run is cancelled through the API
- **THEN** hooks fire once with status `cancelled` and `run_dir` null

#### Scenario: Interrupted run

- **WHEN** the server starts and finds a run directory with no terminal
  event
- **THEN** no hook fires for that run

#### Scenario: Direct engine run fires nothing

- **WHEN** `wosarcherd run "q"` is run directly and ends with `run.done`
- **THEN** no hook fires

### Requirement: Shutdown waits for hooks

On shutdown, after the server has stopped its runs, it SHALL wait for the
hooks that are still running or about to run, including those of runs
that ended because of the shutdown, for at most 20 seconds in total. Hooks
still running after that SHALL be stopped and logged.

#### Scenario: Run cancelled by shutdown

- **WHEN** the server shuts down while a run is running and a hook has no
  `status` filter
- **THEN** the run ends `cancelled` and its hook fires before the server
  exits

#### Scenario: Slow hook at shutdown

- **WHEN** a hook is still running 20 seconds after shutdown began waiting
  for hooks
- **THEN** it is stopped, the stop is logged, and the server exits

### Requirement: Run finished payload

Every hook SHALL receive the same `RunFinished` JSON object:

- `event`: `"run.finished"`
- `run_id`, `status` (`done`, `failed`, or `cancelled`), `query`
- `kind` (`run`, `fork`, or `rerun`), `origin` (`web`, `api`, or `cli`),
  `parent_run_id` (or null), `version`, `profile`
- `created`, `finished`: ISO 8601 timestamps (`finished` is the terminal
  event's time)
- `error`: the `run.failed` error text, or null
- `run_dir`: the run directory's absolute path on the server, or null when
  the run has none
- `report_path`: the absolute path of `report.md` when that file exists,
  else null

#### Scenario: Run stopped before writing

- **WHEN** a run started with `until = "select"` ends with `run.done`
- **THEN** the payload has `"status": "done"` and `report_path` null

#### Scenario: Failed run payload

- **WHEN** a run ends with `run.failed`
- **THEN** the payload's `error` holds the failure text and `report_path`
  is null

### Requirement: Webhook delivery

A `url` hook SHALL send one HTTP POST with `Content-Type: application/json`
and the `RunFinished` body. Configured `headers` SHALL be sent with the
request. When a secret is set, the request SHALL carry
`X-Wosarcher-Signature: sha256=<hex>`, the HMAC-SHA256 of the exact body
bytes keyed by the secret. Redirects SHALL NOT be followed. A 2xx response
SHALL count as delivered.

#### Scenario: Signed webhook

- **WHEN** a run ends `done` and its hook sets `url` and `secret_file`
  naming a file that holds the secret
- **THEN** one POST is sent whose `X-Wosarcher-Signature` equals the
  HMAC-SHA256 of its body under that value, and the body has
  `"status": "done"` and a `report_path`

#### Scenario: Header from a command

- **WHEN** a hook sets
  `headers = { Authorization = { value_command = ["pass", "ntfy"] } }`
- **THEN** the request carries `Authorization` with that command's output

#### Scenario: Redirect is not followed

- **WHEN** the webhook answers 302
- **THEN** no second request is sent and the hook counts as failed

### Requirement: Command execution

A `command` hook SHALL run its argv directly, with no shell and standard
input closed. Its environment SHALL be the server's environment without
any variable whose name starts with `WOSARCHER_`, except
`WOSARCHER_PROFILE`, `WOSARCHER_SOCKET`, and `WOSARCHER_URL`, plus:

- `WA_HOOK_RUN_ID`, `WA_HOOK_STATUS`, `WA_HOOK_QUERY`
- `WA_HOOK_RUN_DIR` and `WA_HOOK_REPORT`: paths, or empty when there are
  none
- `WA_HOOK_PAYLOAD`: the `RunFinished` JSON

Exit code 0 SHALL count as success. A command that runs past its timeout
SHALL be killed. A command that cannot start (missing program, or a value
the system cannot pass in the environment) SHALL count as failed.

#### Scenario: Command gets the run's values

- **WHEN** a run ends `failed` and a hook has
  `command = ["sh", "-c", "echo $WA_HOOK_STATUS > out"]`
- **THEN** `out` holds `failed`

#### Scenario: Server secrets stay out of the command

- **WHEN** the server runs with `WOSARCHER_LLM__API_KEY` and
  `WOSARCHER_PROFILE` set and a command hook fires
- **THEN** the command sees `WOSARCHER_PROFILE` and not
  `WOSARCHER_LLM__API_KEY`

#### Scenario: Query is never interpreted

- **WHEN** a query contains shell metacharacters
- **THEN** it reaches a command hook only as the value of `WA_HOOK_QUERY`,
  never as part of the argv

### Requirement: Hook failures never affect the run

A hook that fails SHALL be logged with the hook's position, its kind, and
the reason, then the next hook SHALL fire. Failures include: a non-2xx
response, a network error, a non-zero exit, a timeout, a program that
cannot start, and a secret source that fails. A log line SHALL NOT include
header values, secrets, the request body, or credentials in the URL. A
hook failure SHALL NOT change the run's events or status. When a run ends
and `hooks.toml` is invalid, the server SHALL log the error and fire no
hooks for that run.

#### Scenario: Webhook endpoint is down

- **WHEN** a run ends `done` and its webhook gets a connection error
- **THEN** the error is logged, the run's status stays `done`, and the next
  hook fires

#### Scenario: Command times out

- **WHEN** a command hook runs longer than its `timeout`
- **THEN** it is killed, the timeout is logged, and the next hook fires

#### Scenario: Invalid file at run end

- **WHEN** `hooks.toml` is invalid and a run ends
- **THEN** the error naming the file is logged, no hook fires, and the
  run's status is unchanged

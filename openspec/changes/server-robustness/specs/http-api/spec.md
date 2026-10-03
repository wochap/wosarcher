## MODIFIED Requirements

### Requirement: Serve command
`wosarcher serve` SHALL start the HTTP server. It SHALL bind `127.0.0.1`
and port `8765` unless `--host`, `--port`, or the `server.host` and
`server.port` settings say otherwise. It SHALL log at the level
`server.log_level` (`debug`, `info`, `warning`, or `error`; default
`info`, environment `WOSARCHER_SERVER__LOG_LEVEL`) to standard error, for
both its own lines and uvicorn's, and SHALL trust proxy headers only from
the addresses in `server.forwarded_allow_ips`.

#### Scenario: Default bind
- **WHEN** the user runs `wosarcher serve` with no options and no `server` settings
- **THEN** the server listens on `127.0.0.1:8765` only

#### Scenario: Port option
- **WHEN** the user runs `wosarcher serve --port 9000`
- **THEN** the server listens on `127.0.0.1:9000`

#### Scenario: Log level from the environment
- **WHEN** the user runs `wosarcher serve` with `WOSARCHER_SERVER__LOG_LEVEL=debug`
- **THEN** the server and uvicorn log at level `debug`

#### Scenario: Invalid log level
- **WHEN** `server.log_level = "loud"`
- **THEN** `wosarcher serve` exits with 2 and an error naming `server.log_level`

### Requirement: Create a run
`POST /api/runs` SHALL accept a multipart form with one `request` field
holding JSON and zero or more `attachments` file fields. The request JSON
SHALL have `query` (required, non-empty), and optional `sources` (`web`,
`files`, or `both`), `until` (a stage name), `profile`, `writing` (any
subset of the writing option fields), and `set` (a list of
`dotted.key=value` overrides). The response SHALL be 201 with the new
`run_id` and its status (`queued` or `running`). Attachment file names
SHALL be reduced to their base name; two attachments with the same base
name SHALL be rejected with 422. A request whose resolved sources are
`files` with no attachment SHALL be rejected with 422
`invalid_attachment` before anything is staged.

#### Scenario: Run with an attachment
- **WHEN** a client posts `request = {"query": "q", "sources": "both"}` and one attachment `notes.md`
- **THEN** the response is 201 with a `run_id`, and the run's process receives `notes.md` as an attachment and `both` as its sources

#### Scenario: Missing query
- **WHEN** a client posts `request = {"query": ""}`
- **THEN** the response is 422 and names `query`

#### Scenario: Path in a file name
- **WHEN** an attachment is uploaded with the file name `../../etc/notes.md`
- **THEN** it is stored as `notes.md` inside the run's staging directory

#### Scenario: Files without attachments
- **WHEN** a client posts `request = {"query": "q", "sources": "files"}` with no attachment
- **THEN** the response is 422 with `error = "invalid_attachment"`, and no run is queued or staged

### Requirement: List and show runs
`GET /api/runs` SHALL list every run in the runs directory, every queued
run, and every run this server remembers as ended without a run directory,
newest first, each with `run_id`, `query`, `status`, `created`,
`parent_run_id`, `version`, `fork_from` (the stage a fork started from, or
null), `profile`, `sources`, `until` (the recipe: null for a full report,
`select` for context), `writing` (the run's resolved writing options),
`duration_s` (seconds from `run.started` to the terminal run event; null
while queued or running, and for interrupted runs), `cost` (the total cost
in dollars from `costs.json`; null when absent), `queue_position` (null
unless queued), `error` (the `run.failed` error text; null unless failed),
and `end_stage` (the stage named by `run.failed` or `run.cancelled`; null
otherwise). Status SHALL be one of `queued`, `running`, `done`, `failed`,
`cancelled`, or `interrupted` (no terminal event and no process owned by
this server). `GET /api/runs/{id}` SHALL return the same summary plus the
redacted `request`, the `costs` when present, and `last_seq` (0 when the
run has no logged event).

#### Scenario: Finished run
- **WHEN** a run's log ends with `run.done`
- **THEN** its status is `done`

#### Scenario: Run left by a crash
- **WHEN** a run's log has no terminal event and no server-owned process runs it
- **THEN** its status is `interrupted`

#### Scenario: Fork lineage
- **WHEN** run B was forked from run A, which is version 1, from the write stage
- **THEN** B's summary has `parent_run_id = A`, `version = 2`, and `fork_from = "write"`

#### Scenario: Duration and cost
- **WHEN** a finished run's `run.started` is at 10:00:00, its `run.done` at 10:02:05, and its `costs.json` total cost is 0.012
- **THEN** its summary has `duration_s = 125` and `cost = 0.012`

#### Scenario: Running run
- **WHEN** a run is running
- **THEN** its summary has `duration_s = null`

#### Scenario: Failed run
- **WHEN** a run's log ends with `run.failed` with stage `fetch` and error `no output`
- **THEN** its summary has `status = "failed"`, `error = "no output"`, and `end_stage = "fetch"`

### Requirement: Delete a run
`DELETE /api/runs/{id}` SHALL remove a finished, failed, cancelled, or
interrupted run's directory and answer 204. A queued run SHALL be removed
from the queue. A run remembered as ended without a run directory SHALL be
forgotten (204). A running run SHALL answer 409 with
`error = "run_active"`.

#### Scenario: Delete running run
- **WHEN** a client deletes a run whose process is running
- **THEN** the response is 409 and the run directory still exists

#### Scenario: Delete finished run
- **WHEN** a client deletes a run with status `done`
- **THEN** the response is 204 and the run no longer appears in `GET /api/runs`

#### Scenario: Delete a run cancelled while queued
- **WHEN** a client deletes a run that was cancelled while queued
- **THEN** the response is 204 and the run no longer appears in `GET /api/runs`

### Requirement: Rerun a run
`POST /api/runs/{id}/rerun` SHALL start, through the run queue, a new
`wosarcher run` with the original run's request (query, sources, `until`,
profile, and its saved overrides, including writing options) and a copy of
the original run directory's attachments, with nothing uploaded again. The
new run SHALL have version 1 and no parent run; it is not a fork. The
response SHALL be 201 with the new `run_id` and its status. An unknown run
SHALL answer 404, a run that is still queued SHALL answer 409, and a run
with sources `files` whose run directory has no attachments SHALL answer
422 `invalid_attachment`.

#### Scenario: Rerun with attachments
- **WHEN** a client reruns a finished run that had the attachment `notes.md`
- **THEN** the response is 201, the new run's process receives a copy of `notes.md` as an attachment, and the new run's summary has `version = 1` and `parent_run_id = null`

#### Scenario: Rerun keeps the writing options
- **WHEN** the original run was started with tone `critical` and the global tone is now `formal`
- **THEN** the rerun's resolved tone is `critical`

#### Scenario: Rerun of a files run without attachments
- **WHEN** a client reruns a run with sources `files` whose `attachments/` directory is missing
- **THEN** the response is 422 with `error = "invalid_attachment"`

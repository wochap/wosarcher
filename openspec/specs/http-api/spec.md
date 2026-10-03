# http-api Specification

## Purpose

Exposes runs, artifacts, global defaults, profiles, and provider health as a
JSON API on the same origin as the frontend, so the browser UI and remote
scripts drive the same `wosarcher run` code path as the CLI.

## Requirements

### Requirement: Serve command
`wosarcher serve` SHALL start the HTTP server. It SHALL bind `127.0.0.1`
and port `8765` unless `--host`, `--port`, or the `server.host` and
`server.port` settings say otherwise.

#### Scenario: Default bind
- **WHEN** the user runs `wosarcher serve` with no options and no `server` settings
- **THEN** the server listens on `127.0.0.1:8765` only

#### Scenario: Port option
- **WHEN** the user runs `wosarcher serve --port 9000`
- **THEN** the server listens on `127.0.0.1:9000`

### Requirement: API prefix and errors
Every JSON route and the event WebSocket SHALL live under `/api`. Error
responses SHALL be JSON objects with an `error` code and a human-readable
`detail`. An unknown run ID SHALL answer 404 with `error = "run_not_found"`.
An invalid request body SHALL answer 422 and name each invalid field.

#### Scenario: Unknown run
- **WHEN** a client sends `GET /api/runs/does-not-exist`
- **THEN** the response is 404 with `{"error": "run_not_found", "detail": ...}`

#### Scenario: Invalid field
- **WHEN** a client creates a run with `"writing": {"words": 0}`
- **THEN** the response is 422 and the detail names `writing.words`

### Requirement: Create a run
`POST /api/runs` SHALL accept a multipart form with one `request` field
holding JSON and zero or more `attachments` file fields. The request JSON
SHALL have `query` (required, non-empty), and optional `sources` (`web`,
`files`, or `both`), `until` (a stage name), `profile`, `writing` (any
subset of the writing option fields), and `set` (a list of
`dotted.key=value` overrides). The response SHALL be 201 with the new
`run_id` and its status (`queued` or `running`). Attachment file names
SHALL be reduced to their base name; two attachments with the same base
name SHALL be rejected with 422.

#### Scenario: Run with an attachment
- **WHEN** a client posts `request = {"query": "q", "sources": "both"}` and one attachment `notes.md`
- **THEN** the response is 201 with a `run_id`, and the run's process receives `notes.md` as an attachment and `both` as its sources

#### Scenario: Missing query
- **WHEN** a client posts `request = {"query": ""}`
- **THEN** the response is 422 and names `query`

#### Scenario: Path in a file name
- **WHEN** an attachment is uploaded with the file name `../../etc/notes.md`
- **THEN** it is stored as `notes.md` inside the run's staging directory

### Requirement: Run request precedence
A run started by the server SHALL resolve its configuration as the CLI does
(defaults, profile, environment), then apply the global settings, then the
request's `sources` and `writing` fields, then the request's `set`
overrides, each later layer winning. The profile SHALL be read when the run
process starts, so profile edits apply without restarting the server.

#### Scenario: Request overrides global default
- **WHEN** the global settings have tone `formal` and a run request has `"writing": {"tone": "critical"}`
- **THEN** the run's resolved tone is `critical`

#### Scenario: Global default applies
- **WHEN** the global settings have words 600 and a run request has no `writing`
- **THEN** the run's resolved words is 600

### Requirement: List and show runs
`GET /api/runs` SHALL list every run in the runs directory and every queued
run, newest first, each with `run_id`, `query`, `status`, `created`,
`parent_run_id`, `version`, `fork_from` (the stage a fork started from, or
null), `profile`, `sources`, `until` (the recipe: null for a full report,
`select` for context), `writing` (the run's resolved writing options),
`duration_s` (seconds from `run.started` to the terminal run event; null
while queued or running, and for interrupted runs), `cost` (the total cost
in dollars from `costs.json`; null when absent), and `queue_position`
(null unless queued). Status SHALL be one of `queued`, `running`, `done`,
`failed`, `cancelled`, or `interrupted` (no terminal event and no process
owned by this server). `GET /api/runs/{id}` SHALL return the same summary
plus the redacted `request`, the `costs` when present, and `last_seq`.

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

### Requirement: Delete a run
`DELETE /api/runs/{id}` SHALL remove a finished, failed, cancelled, or
interrupted run's directory and answer 204. A queued run SHALL be removed
from the queue. A running run SHALL answer 409 with
`error = "run_active"`.

#### Scenario: Delete running run
- **WHEN** a client deletes a run whose process is running
- **THEN** the response is 409 and the run directory still exists

#### Scenario: Delete finished run
- **WHEN** a client deletes a run with status `done`
- **THEN** the response is 204 and the run no longer appears in `GET /api/runs`

### Requirement: Artifacts allowlist
`GET /api/runs/{id}/artifacts/{name}` SHALL serve only these names:
`request.json`, `files.jsonl`, `plan.json`, `initial.jsonl`, `hits.jsonl`,
`pages.jsonl`, `chunks.jsonl`, `candidates.jsonl`, `scores.jsonl`,
`context.json`, `report.md`, `report.json`, `events.jsonl`, `costs.json`. JSON files SHALL be served as
`application/json`, JSONL as `application/x-ndjson`, and Markdown as
`text/markdown`, all UTF-8. Any other name, or a listed file that does not
exist, SHALL answer 404.

#### Scenario: Allowed artifact
- **WHEN** a client requests `context.json` of a finished run
- **THEN** the response is 200 with the file content and `application/json`

#### Scenario: Structured report
- **WHEN** a client requests `report.json` of a finished run
- **THEN** the response is 200 with the report body, references, and `application/json`

#### Scenario: Name outside the allowlist
- **WHEN** a client requests the artifact `..%2Fother%2Freport.md` or `attachments`
- **THEN** the response is 404 and no file outside the allowlist is read

### Requirement: Fork a run
`POST /api/runs/{id}/fork` SHALL accept JSON with `from` (a stage name) and
optional `writing`, `set`, and `profile`, and start
`wosarcher fork <id> --from <stage>` with those overrides through the run
queue. The response SHALL be 201 with the new `run_id`. Forking a run that
is queued or running SHALL answer 409; an unknown stage name SHALL answer
422 listing the stages.

#### Scenario: Rewrite with a new tone
- **WHEN** a client forks a finished run with `{"from": "write", "writing": {"tone": "critical"}}`
- **THEN** a new run starts from the write stage with tone `critical` and records the parent run ID

#### Scenario: Fork of active run
- **WHEN** a client forks a run whose status is `running`
- **THEN** the response is 409

### Requirement: Rerun a run
`POST /api/runs/{id}/rerun` SHALL start, through the run queue, a new
`wosarcher run` with the original run's request (query, sources, `until`,
profile, and its saved overrides, including writing options) and a copy of
the original run directory's attachments, with nothing uploaded again. The
new run SHALL have version 1 and no parent run; it is not a fork. The
response SHALL be 201 with the new `run_id` and its status. An unknown run
SHALL answer 404 and a run that is still queued SHALL answer 409.

#### Scenario: Rerun with attachments
- **WHEN** a client reruns a finished run that had the attachment `notes.md`
- **THEN** the response is 201, the new run's process receives a copy of `notes.md` as an attachment, and the new run's summary has `version = 1` and `parent_run_id = null`

#### Scenario: Rerun keeps the writing options
- **WHEN** the original run was started with tone `critical` and the global tone is now `formal`
- **THEN** the rerun's resolved tone is `critical`

### Requirement: Global settings
`GET /api/settings` SHALL return the global defaults: `writing` (all writing
option fields) and `sources`. `PUT /api/settings` SHALL replace them after
validation and persist them in `server-settings.json` in the wosarcher
config directory, so they survive a restart. Built-in writing defaults
SHALL apply when the file does not exist.

#### Scenario: Defaults persist
- **WHEN** a client puts settings with words 800 and the server restarts
- **THEN** `GET /api/settings` returns words 800

#### Scenario: Invalid settings
- **WHEN** a client puts settings with `citation_marker = "footnote"`
- **THEN** the response is 422 and the stored settings are unchanged

### Requirement: Profiles
`GET /api/profiles` SHALL return every profile with its `name`, its
`source` (`builtin` or `user`), and whether it is `active`.

#### Scenario: Active profile marked
- **WHEN** the stored default profile is `cloud`
- **THEN** the `cloud` entry has `active = true` and every other entry `false`

### Requirement: Provider health
`GET /api/providers/health` SHALL run the `wosarcher doctor` checks for the
active profile, or for the profile named by the `profile` query parameter,
and return them as JSON: the profile name, the doctor's warnings, and one
entry per provider with `role`, `provider`, `url`, `model`, `device`,
`status`, `latency_ms`, and `detail`. The status SHALL be `down` for a
failed probe, `skipped` for a built-in provider, `degraded` for a probe
that succeeded but took more than 1000 ms or whose model cannot be unloaded
although a release is configured, and `ok` otherwise. No secret SHALL
appear in the response. When the checks cannot run (timeout or unreadable
output), the response SHALL be 502 with the reason.

#### Scenario: Health of a named profile
- **WHEN** a client requests `GET /api/providers/health?profile=cloud`
- **THEN** the response lists the checks for the `cloud` profile

#### Scenario: Slow provider
- **WHEN** the search probe succeeds in 1840 ms
- **THEN** the search entry has `status = "degraded"` and `latency_ms = 1840`

#### Scenario: Unreachable provider
- **WHEN** the score probe fails with a connection error
- **THEN** the response is 200 and the score entry has `status = "down"` and the error as `detail`

### Requirement: Static frontend
When the frontend build directory (`server.static_dir`, default `web/dist`)
exists, the server SHALL serve its files from `/`, and SHALL answer any
other `GET` outside `/api` that matches no file with `index.html`. When the
directory does not exist, the API SHALL still work and `/` SHALL answer 404.

#### Scenario: Frontend route
- **WHEN** the build exists and a browser requests `/runs/abc123`
- **THEN** the response is `index.html`

#### Scenario: API not shadowed
- **WHEN** the build exists and a client requests `GET /api/runs`
- **THEN** the response is the JSON run list

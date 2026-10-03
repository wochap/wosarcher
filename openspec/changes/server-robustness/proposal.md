# Proposal: server-robustness

## Why

The first live deployment and the Fable review found that one bad run can
freeze the server's queue until a restart (an unparsable event line, a
standard-error line over 64 KiB, or a crash inside `RunManager._finish`), that
a failed or cancelled run can look "running" forever, that cancelling a
finished run answers an opaque 409, and that the server logs nothing but
uvicorn access lines, so failures cannot be diagnosed from `journalctl` or
`docker logs`. Behind the README's Caddy + Docker setup every state-changing
request answers 403 because uvicorn trusts forwarded headers only from
`127.0.0.1`. These must be fixed before the server is used for real runs.

## What Changes

- **Queue never stalls** (Fable 2.1, 5.3): the run coroutine always finalises
  the run (terminal event, tail closed, staging removed, slot freed, next run
  started) whatever fails; standard-error lines of any length are read and
  shortened; unparsable `events.jsonl` lines are skipped with a log warning
  by the tail and by the store, and an append after a partial last line
  starts on a new line.
- **`seq` across stores** (Fable 5.2): `RunStore.append_event` reads the last
  logged `seq` from the end of `events.jsonl` on every append, so two stores
  (or processes appending one after another) never repeat a `seq`.
- **Run status without the socket**: a run that ended before its run
  directory existed (cancelled while queued, or a process that exited
  early) stays visible to `GET /api/runs/{id}`, `GET /api/runs`, and the
  event socket as `cancelled` or `failed` until the server restarts, instead
  of becoming 404. Run summaries gain `error` and `end_stage` (from
  `run.failed` / `run.cancelled`).
- **Cancel of a finished run** answers 409 with a `RunNotActive` body that
  carries the run's current `status`, so the UI can refresh instead of
  showing an error.
- **Socket on a run that just ended** (Fable 3.3): the socket looks the run
  up after accepting, so a run that ends during the handshake is replayed and
  closed, never left hanging.
- **Logging**: server log lines for run lifecycle (queued, started, done,
  failed, cancelled, with `run_id`); each run process's standard error is
  forwarded to the server log prefixed with the run ID; the run process
  writes stage start/done/failed lines, warnings, and full page-failure
  reasons to standard error when the live progress view is not shown;
  `server.log_level` (`WOSARCHER_SERVER__LOG_LEVEL`); new CLI command
  `wosarcher logs <run-id> [--follow]`.
- **Short page-failure reasons**: `page.failed.reason` is the first line of
  the error, at most 200 characters; the full text goes to the run's
  standard error and so to the server log.
- **Reverse proxy** (Fable 2.6, 3.4): `server.forwarded_allow_ips` (default
  `["127.0.0.1"]`) is passed to uvicorn; README documents values for Caddy on
  the host and for Docker.
- **Small fixes** (Fable 3.1, 5.7): a cancelled run writes `costs.json`;
  session-cookie signatures are compared as bytes (a non-ASCII cookie is 401,
  not 500); `POST /api/runs` with `sources = "files"` and no attachment is
  422 before anything is queued.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `run-queue`: cancel 409 body with status; finalisation always runs;
  standard-error handling and forwarding; lifecycle log lines; runs that end
  without a run directory are remembered.
- `http-api`: serve options (`server.log_level`, `server.forwarded_allow_ips`);
  `error` and `end_stage` in summaries; runs without a directory in list,
  show, and delete; `files` without attachments rejected.
- `event-streaming`: socket for a run that ended during the handshake or
  without a directory; terminal events that are not logged follow the
  live-only `seq` rule.
- `run-events`: `seq` read from the log on every append; unreadable lines
  skipped; append after a partial line.
- `run-lifecycle`: costs on cancellation; short `page.failed` reasons with
  the full text on standard error; stage diagnostics on standard error.
- `cli-run`: standard-error log lines when no progress view is shown; new
  `wosarcher logs` command.
- `admin-auth`: trusted proxy addresses; malformed session cookies are 401.

## Non-goals

- Frontend changes (run status from `GET /api/runs/{id}`, Cancel hiding,
  reconnect back-off, terminal events with `seq` 0): change
  `ui-run-state-fixes`, which relies on the contracts recorded in this
  change's design.md.
- Structured (JSON) logging, log files, or log rotation: the server logs to
  standard error and the supervisor (journald, Docker) keeps the logs.
- Locking `events.jsonl` against two processes appending at the same
  moment; the server only appends after the run process exited.
- Persisting runs that ended without a run directory across restarts.
- Other Fable items: hidden attachment names (3.6), deleting a CLI run
  that is still writing (3.7), listing speed (3.8), fork lineage (1.3).

## Impact

- Code: `src/wosarcher/server/manager.py`, `tail.py`, `stream.py`,
  `routes.py`, `staging.py`; `src/wosarcher/cli/serve.py`, `cli/run.py`,
  new `cli/logs.py`, `cli/__init__.py`; `src/wosarcher/store/__init__.py`;
  `src/wosarcher/runner/__init__.py`, `runner/steps.py`;
  `src/wosarcher/auth.py`; `src/wosarcher/config.py` (`ServerConfig`);
  `src/wosarcher/models.py` (`RunSummary.error`, `RunSummary.end_stage`,
  new `RunNotActive` in `CONTRACTS`).
- API: new 409 body for cancel; two new summary fields; `web/src/api/generated.ts`
  regenerates (type drift check).
- Tests: `tests/server/` (new fake modes), `tests/test_store.py`,
  `tests/runner/test_runner.py`, `tests/auth/test_session.py`,
  `tests/test_cli_serve.py`, new `tests/test_cli_logs.py`.
- Docs: `docs/design.md` sections "Patterns used, and only these",
  "Commands", "Events", "Errors and cancellation", "Server",
  "Authentication" (Transport), "Package layout"; README "Production"
  (watching logs) and "Docker" (reverse proxy).
- No new dependency (stdlib `logging`).

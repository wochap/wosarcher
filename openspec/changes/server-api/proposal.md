# Proposal

## Why

The frontend and remote scripts need to start, watch, cancel, and fork runs
over HTTP and WebSocket. The CLI already does all the work (`wosarcher run`,
`wosarcher fork`, the run store, events); the server only has to start those
commands, queue them so GPU stages are not oversubscribed, and stream their
events to browsers that may disconnect and reconnect at any time.

## What Changes

- `wosarcher serve [--host] [--port]`: a FastAPI app on `127.0.0.1:8765` by
  default. Routes in this change are open; `admin-auth` protects them next.
- JSON API under `/api`: create, list, show, delete, cancel, fork, and
  rerun runs (a rerun is a new run with the original request and a copy of
  its attachments); run summaries carry the recipe (`until`), duration,
  cost, `fork_from`, and the writing options; download run artifacts from
  a fixed allowlist (including `report.json`); read and update global
  defaults (writing options and sources); list profiles; check provider
  health (the `wosarcher doctor` checks).
- Run queue: each run is a `wosarcher run` or `wosarcher fork` subprocess.
  At most `server.max_concurrent_runs` (default 1) run at once; the rest
  wait in FIFO order and report `run.queued` with their position. Cancel
  sends SIGTERM (SIGKILL after a grace period). A subprocess that exits
  without a terminal event gets a `run.failed` appended by the server.
- Event streaming: `WS /api/runs/{id}/events?since=<seq>` replays logged
  events after `seq`, then sends a `report.snapshot` of the report so far,
  then streams new events and live `report.delta` text until the run ends.
- Static frontend: when `web/dist` exists, it is served from the same
  origin, with `index.html` for unknown non-API paths.
- Additions to earlier code that this change needs:
  - `Settings` gains a `server` block (`host`, `port`,
    `max_concurrent_runs`, `static_dir`).
  - The API request and response models live in `models.py` and are
    included in `wosarcher schema`, so the frontend generates its types.
- Used as they are from earlier changes: `--run-id` on `wosarcher run` and
  `wosarcher fork`, `fork --profile`, `report.md` written as it streams,
  run listing that skips dot directories, `store.new_run_id()`,
  `RunStore.append_event` (run-orchestration), and `wosarcher doctor
  --json` printing a `DoctorReport` (provider-adapters).

## Non-goals

- Authentication, sessions, tokens, Origin and Host checks: `admin-auth`.
- Running pipeline stages inside the server process. Every run is a
  subprocess; the server never imports `runner` to execute a run.
- Persisting the queue in a database. Queued requests are staged on disk
  and re-queued on restart; there is no other server state.
- Multiple server instances sharing one runs directory.
- The frontend itself (`frontend-shell`, `frontend-run`).

## Capabilities

### New Capabilities

- `http-api`: the JSON routes, the request shape for new runs and forks,
  run summaries and status, the artifact allowlist, global settings,
  profiles, provider health, static frontend serving, and `wosarcher serve`.
- `event-streaming`: the run event WebSocket: replay from a sequence
  number, report snapshot, live report deltas, and when the stream closes.
- `run-queue`: how runs are started as subprocesses, limited, queued,
  cancelled, and finalised when a process dies.

### Modified Capabilities

None. (`--run-id`, `fork --profile`, and incremental `report.md` writes
already exist in run-orchestration; this change uses them unchanged.)

## Impact

- New code: `src/wosarcher/server/` package (`__init__.py` app factory,
  `manager.py` queue and subprocesses, `tail.py` run tailer, `routes.py`,
  `meta.py`, `stream.py`, `settings.py`), `serve` command in the `cli/`
  package, tests with a fake run command in `tests/server/`.
- Changed code: `config.py` (`ServerConfig` block), `models.py` (API
  models), the `schema` command (includes them).
- New dependencies: `fastapi`, `uvicorn`, `python-multipart` (FastAPI
  needs it to parse multipart forms). Dev: none (TestClient uses httpx,
  already a dependency).
- `scripts/check_architecture.py`: no change; `server` is already in
  `ALLOWED` and a package counts as one part.
- docs/design.md sections implemented: Server, Events (`run.queued`,
  `report.delta`, `report.snapshot`), Frontend decisions (same-origin
  socket URL), Tech stack (FastAPI, uvicorn).
- docs/design.md changes: API routes live under `/api` (so frontend routes
  like `/runs/<id>` never collide with JSON routes); `POST
  /api/runs/{id}/rerun`; `run.queued` and
  `report.delta` are live-only and never in `events.jsonl`; global
  defaults are stored in `server-settings.json` and apply to runs started
  by the server.

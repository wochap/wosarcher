# Design: server-robustness

## Context

See proposal.md for the motivation. Current state that shapes the approach:

- `RunManager._run` (`server/manager.py`) guards only
  `create_subprocess_exec`. `RunTail.poll()` → `publish_events` calls
  `parse_event` on every line and raises on anything unknown; `_finish`
  calls `RunStore.append_event`, which re-reads the whole log with
  `parse_event`. Any exception kills the task before `tail.close()`,
  `staging.remove`, `self.running.pop`, and `_pump`, so with
  `max_concurrent_runs = 1` the queue stops.
- `_read_stderr` iterates `process.stderr` with the default 64 KiB
  `StreamReader` limit; a longer line raises `ValueError` in the reader,
  `await reader` re-raises, same outcome.
- `RunStore.append_event` caches `last_seq[run_id]` per store instance;
  only the first append of an instance reads the file. The server works
  around it with `self.store.last_seq.pop(...)` before appending.
- `stream.events` reads `manager.active(run_id)` before
  `await socket.accept()` and subscribes after it; `RunTail.close()` has
  already emptied `subscribers`, so a late subscriber waits forever.
- A queued run that is cancelled, or a process that exits before creating
  `runs/<id>/`, leaves nothing on disk: `GET /api/runs/{id}` answers 404
  right after the 201, and the socket closes with 4404.
- `cancel_run` answers `RouteError(409, "run_not_active", ...)` without the
  status.
- The run process prints nothing to standard error when no progress view is
  shown (the server's case); the server keeps the last 20 stderr lines in
  memory and logs nothing itself except login failures (`server/login.py`).
- `cli/serve.py` calls `uvicorn.run(app, host=..., port=..., proxy_headers=True)`;
  uvicorn's `forwarded_allow_ips` then defaults to `127.0.0.1` (uvicorn
  0.54 accepts addresses, CIDR networks, and `*`).

## Goals / Non-Goals

**Goals:** a run can never stop the queue; every run the UI was told about
has a status it can read over HTTP; the server log tells what each run did;
the documented Caddy + Docker setup works.

**Non-Goals:** see proposal.md Non-goals. No log framework beyond stdlib
`logging`; no new dependency.

## Contracts the UI depends on (change `ui-run-state-fixes`)

These are fixed by this change; the frontend change relies on them exactly.

### `POST /api/runs/{id}/cancel`

| Run state | Status | Body |
|---|---|---|
| running | 202 | `{"run_id": "<id>", "result": "signalled"}` |
| queued | 200 | `{"run_id": "<id>", "result": "dequeued"}` |
| done, failed, cancelled, interrupted (incl. remembered dir-less runs) | 409 | `RunNotActive`: `{"error": "run_not_active", "detail": "run <id> is not queued or running (status <status>)", "run_id": "<id>", "status": "<RunStatus>"}` |
| unknown | 404 | `{"error": "run_not_found", "detail": "no run <id>"}` |

`RunNotActive` is a new model in `models.py` (fields `error`, `detail`,
`run_id`, `status: RunStatus`), added to `CONTRACTS`, so it appears in
`wosarcher schema` and `web/src/api/generated.ts`. The UI on a 409 reads
`status`, refreshes the run with `GET /api/runs/{id}`, and hides Cancel; it
shows no error toast.

### `GET /api/runs/{id}` (`RunDetail`) fields the UI reads

- `status`: `queued | running | done | failed | cancelled | interrupted`.
  Terminal for the UI: `done`, `failed`, `cancelled`, `interrupted`
  (Cancel hidden). `queued` and `running` are the only active states.
- `error: string | null` (new, on `RunSummary`): the `run.failed`
  `data.error` text; null unless `status == "failed"`.
- `end_stage: Stage | null` (new, on `RunSummary`): `data.stage` of the
  last `run.failed` or `run.cancelled`; null otherwise (also null when that
  event names no stage, e.g. a server-appended `run.failed`).
- `last_seq: int`: the last logged `seq` (0 when none or no run directory).
  The UI reconnects with `since = max(its own lastSeq, ...)` as today; a
  `status` that is terminal means "do not reconnect, show the end state".
- `queue_position`, `duration_s`, `cost`: unchanged.
- A run cancelled while queued, or whose process exited before creating its
  directory, answers 200 with `status` `cancelled` / `failed`, `request`
  null, `costs` null, `last_seq` 0, until the server restarts or the run is
  deleted. After a restart it is 404 `run_not_found` (UI: not-found state).

The same `error` and `end_stage` appear in every `GET /api/runs` row and in
`wosarcher runs --json` (`RunStore.summary` fills them).

### Event socket: terminal events and `seq`

- Logged terminal events (`run.done`, `run.failed`, `run.cancelled` in
  `events.jsonl`, including the ones the server appends after a crash or
  SIGKILL) carry their real, increasing `seq`.
- Terminal events that are not logged, i.e. the `run.cancelled` of a run
  cancelled while queued and the `run.failed` / `run.cancelled` of a run
  that never got a run directory, are sent with `seq` = the last logged
  `seq` sent to that client, which is 0 for those runs (they have no log).
  **Rule for clients: apply `run.done`, `run.failed`, and `run.cancelled`
  regardless of `seq`, without moving `lastSeq`.** Every other event keeps
  the existing dedupe-by-`seq` rule.
- After any terminal event the server closes with 1000. A socket opened on
  a remembered dir-less run gets exactly one terminal event (seq 0) and
  1000. A socket opened on an unknown run (or a dir-less run after a server
  restart) gets 4404. A socket never stays open on an ended run.
- Close codes are unchanged: 1000 end, 4404 unknown, 4408 too slow
  (reconnect with `since`), 1008 refused by the guard. Any other close
  (including a failed upgrade, which the browser reports as 1006) is a
  transport failure; the back-off and "live updates unavailable" behaviour
  belongs to `ui-run-state-fixes`.

## Decisions

### 1. Finalisation in `finally`, and an exception-safe `_finish`

`_run` becomes `try: spawn, poll loop, await reader; except Exception:
log.exception(...) finally: self._finish(active, code)`. Each poll in the
loop is wrapped so an unexpected error is logged and the loop keeps
waiting for the process to exit (otherwise a poll error would finish the
run while the process still runs). `_finish` does the fallible work (final
poll, append of the terminal event) inside `try/except Exception` with
`log.exception`, then always cancels the kill timer, closes the tail,
removes staging, pops `running`, and pumps. Alternative: a supervisor task
that restarts dead run tasks; rejected, more moving parts for the same
guarantee.

### 2. Tolerant parsing in one place each

`RunTail.publish_events` and `RunStore.read_events` catch the parse error
(`ValueError`, which pydantic's `ValidationError` subclasses) per line and
skip it; the tail logs a warning with the run ID and the first 200
characters, the store does not log (it is used by the CLI too, and the
server's tail already reported the line). `parse_event` itself keeps
rejecting unknown types (run-events "Unknown type rejected").

### 3. `seq` from the end of the file on every append

`RunStore.append_event` drops the `last_seq` cache and calls a new
`RunStore.tail_seq(run_id)` that reads `events.jsonl` backwards in 8 KiB
blocks until it has a complete line (a line followed by `\n`) that parses,
and returns its `seq` (0 for a missing or empty file). Before writing, when
the file is non-empty and its last byte is not `\n`, it writes `\n` first,
so a partial line from a killed process becomes its own (skipped) line.
`last_logged_seq` uses `tail_seq` too, and `manager.py` drops its
`self.store.last_seq.pop(...)`. Cost: one small read per append (events are
at most a few thousand per run). Alternative: file locking (`fcntl`) to
also cover simultaneous writers; rejected, there is no simultaneous writer
today and the run-store must stay simple.

### 4. Standard error read in chunks, cut, and forwarded

`_read_stderr` reads `process.stderr.read(65536)` in a loop, splits on
`\n`, and handles each complete line with `_stderr_line(active, text)`:
cut to `STDERR_MAX_CHARS = 4000` plus `…`, appended to the 20-line deque,
and logged as `log.info("run %s: %s", run_id, text)`. A pending partial
line longer than the cap is emitted cut, and the rest up to the next `\n`
is dropped. No `limit=` tuning, so no line length can raise.

### 5. Server logging with stdlib `logging`

Module loggers `logging.getLogger(__name__)` in `server/manager.py` and
`server/tail.py` (as `server/login.py` already does). `cli/serve.py`
configures the root logger once with
`logging.basicConfig(level=settings.server.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)`
and passes `log_level=settings.server.log_level` to `uvicorn.run`, which
keeps its own format for its loggers. Lifecycle lines (exact wording fixed
so tests can match):

- `run <id> queued (position <n>)` (info) in `submit` when the run did not
  start at once;
- `run <id> started: <run|fork> pid <pid>` (info) after spawning;
- `run <id> done` (info), `run <id> cancelled` (info; also
  `run <id> cancelled while queued`), `run <id> failed in <stage or ->: <first line of error>`
  (warning) in `_finish`, from the tail's terminal event or the event the
  server appended. The tail keeps the last terminal event it published in
  `RunTail.terminal_event` (replacing the `terminal: bool` flag).

`ServerConfig.log_level: Literal["debug", "info", "warning", "error"] = "info"`;
the environment override `WOSARCHER_SERVER__LOG_LEVEL` works through the
existing resolution. `ServerConfig.forwarded_allow_ips: list[str] = ["127.0.0.1"]`,
passed as `forwarded_allow_ips=",".join(...)` with `proxy_headers=True`.

### 6. Diagnostics from the run process

New `cli/logs.py` holds:

- `event_line(event) -> str`: `"<HH:MM:SS> <stage or -> <type> <summary>"`
  with summary per type: `run.started` query; `stage.started`
  `provider=<p> device=<d or ->`; `stage.done` `count=<n> <s>s provider=<p>`
  plus `skipped` / `copied from <id>` / `<k> warnings`; `stage.failed`
  `<error> -> next=<next or none>`; `run.failed` `<stage>: <error>`;
  `run.cancelled` `<stage>`; `run.done` `until=<until or write>`;
  `page.fetched` `<url> <chars> chars[ cached]`; `page.failed`
  `<url>: <reason>`; `hit.found` `<url>`; `plan.ready` `<n> sub-queries`;
  `passages.scored` `<query_id> kept <kept>/<scored> by <scorer>`;
  `resource.*` `<device> <released_stage>`; `stage.progress`
  `<done>/<total> failed <failed>`; others the JSON of `data`. Newlines
  become spaces; the summary is cut to 160 characters with `…`.
- `stderr_listener(logger) -> Listener`: logs `event_line` at INFO for
  `run.*`, `stage.started`, `stage.done`, `stage.failed`, `resource.*`
  (WARNING for `run.failed` and `stage.failed`), and one WARNING per
  `stage.done` warning: `warning <stage>: <text>`.
- `logs(run_id, follow, profile, set_)`: the `wosarcher logs` command.

`cli/run.py` `start()` configures the `wosarcher` logger: when the progress
view is not shown, a `StreamHandler(sys.stderr)` with format
`"%(levelname)s %(message)s"` at INFO and the `stderr_listener`; when it is
shown, a `logging.NullHandler` and `propagate = False`, so Python's
last-resort handler cannot print under the live view. `runner/steps.py`
`fetch` logs the full reason with
`logging.getLogger(__name__).warning("fetch %s failed: %s", url, reason)`
and emits `page.failed` with `short_reason(reason)` (first line, at most
200 characters, `…` when cut), a small helper in `runner/steps.py`. The
server forwards these lines (Decision 4), giving
`... INFO wosarcher.server.manager: run <id>: WARNING fetch https://x failed: <full text>`.

`wosarcher logs` resolves settings like `runs`, reads with
`RunStore.read_events` (tolerant), prints each line with `typer.echo`, and
with `--follow` polls every 0.5 s with `read_events(run_id, since=last)`
until a terminal event. Unknown run: `fail(..., 2)`.

### 7. Runs that end without a run directory

`RunManager.ended: OrderedDict[str, EndedRun]` with
`EndedRun(staged: StagedRun, event: RunFailed | RunCancelled)`, capped at
`ENDED_LIMIT = 100` (oldest dropped). Filled by `cancel()` for a dequeued
run and by `_finish` when `runs/<id>/` does not exist. `routes.summary`
checks it after the store and the active runs and builds the summary from
`staged_summary` with `status`, `error`, and `end_stage` from the event.
`delete_run` pops it (204). `cancel_run` answers 409 with its status.
`stream.events` sends `ended.event` and closes 1000. `list_runs` includes
its keys. In memory only: a restart forgets them (documented).
Alternative: write a minimal run directory for such runs; rejected, the
CLI owns run directories and `--run-id` must stay free for the process.

### 8. Socket lookup after accept

`stream.events` calls `await socket.accept()` first, then reads
`manager.active(run_id)`, `manager.ended`, and the store, and subscribes
with no `await` in between, so the tail cannot close between the lookup
and the subscription (all on one event loop). No `closed` flag is needed.

### 9. Cancel 409 body

`cancel_run` builds `RunNotActive` from `routes.summary(state, run_id).status`
and returns it with `JSONResponse(..., status_code=409)`; `RouteError`
stays as is (it has no extra fields). Other 409s are unchanged.

### 10. Small fixes

- `Runner.run`: in the `asyncio.CancelledError` branch call
  `self.write_costs(run_id)` (inside `suppress(Exception)`) before emitting
  `run.cancelled`.
- `auth.verify_session`: compare `sig.encode()` with the expected signature
  encoded; `compare_digest` on two `str` raises `TypeError` for non-ASCII.
- `staging.stage_run` and `staging.stage_rerun` raise
  `StagingError("sources files needs at least one attachment")` when the
  resolved sources are `files` and there are no uploads / no copied
  `attachments/`; `create_run` already maps `StagingError` to 422
  `invalid_attachment`, and `rerun_run` gains the same mapping. The check
  runs before any file is written (for rerun: the staging directory is
  removed again on failure).

## Risks / Trade-offs

- [A skipped event line hides a real bug] → the tail logs each skipped line
  with the run ID; tests cover the warning.
- [Reading the tail of the file on every append costs a seek and a read] →
  at most a few thousand appends per run; negligible next to HTTP calls.
- [Remembered dir-less runs vanish on restart] → documented; the UI treats
  404 as not found; DELETE forgets them earlier.
- [`forwarded_allow_ips = ["*"]` lets any client spoof its IP and scheme]
  → README recommends the proxy's address or the bridge network only, and
  `*` only when nothing but the proxy can reach the port.
- [Forwarding every stderr line at info can be chatty] → the run process
  writes only stage-level lines and warnings; `server.log_level = "warning"`
  hides them.

## Migration Plan

No data migration. Existing `events.jsonl` files read the same. The new
summary fields default to null, so old clients ignore them. Rollback is a
revert.

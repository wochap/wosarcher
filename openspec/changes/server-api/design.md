# Design

## Context

Before this change the CLI can run, fork (`--profile`, `--run-id`), and
list runs, and `python -m wosarcher` works; the runner writes `runs/<id>/`
with `request.json` (a `RunRecord`: `request` = `RunRequest(query,
sources, until, attachments)`, `profile`, `overrides`, `settings`,
`parent_run_id`, `fork_from`, `version`), `events.jsonl` (the store's
`append_event` assigns `seq`), `report.md` (appended as it streams, then
replaced by the rendered report), `report.json`, and `costs.json`
(`total` is a `UsageTotals` with `cost` in dollars), and handles SIGTERM
by cancelling and logging `run.cancelled`. `RunStore.list_runs` skips dot
directories and `store.new_run_id()` generates IDs. Event types are
Pydantic models from run-orchestration. `wosarcher doctor --json` prints
provider-adapters' `DoctorReport`.
`scripts/check_architecture.py` already allows `server` to import every
lower part. See proposal.md for scope and the specs for behaviour.

## Goals / Non-Goals

**Goals:**

- The server is a thin process manager plus file tailer; all research work
  stays in `wosarcher run`.
- One place decides ordering of events for a client, so replay plus live
  streaming has no gaps and no duplicates.
- Tests run real subprocesses of a small fake command, never providers.

**Non-Goals:**

- Watching runs started by the CLI live. They are replayed and the socket
  closes (spec: Stream end).
- Authentication of any kind (admin-auth).

## Decisions

### Package `src/wosarcher/server/`

The routes, the queue, the tailer, and the WebSocket together are well over
300 lines, so the server is a package from the start:

```
server/
  __init__.py   # create_app(settings, runs_dir, config_dir, command) -> FastAPI; static mount; lifespan
  manager.py    # RunManager: queue, staging, subprocesses, cancel, finalise
  tail.py       # RunTail: polls events.jsonl and report.md, fans out to subscribers
  routes.py     # /api/runs routes (create, list, show, delete, cancel, fork, artifacts)
  meta.py       # /api/settings, /api/profiles, /api/providers/health
  stream.py     # WS /api/runs/{id}/events
  settings.py   # ServerSettings model, load/save server-settings.json
```

Each file stays under about 250 lines. A package is one part (`server`) for
the architecture check, so `ALLOWED` does not change. No globals: the
`RunManager` lives on `app.state` and routes reach it through a small
FastAPI dependency function.

### The run command is injected

`create_app(..., command: list[str])` takes the argv prefix used to start
children. Production passes `[sys.executable, "-m", "wosarcher"]`; tests pass
`[sys.executable, "tests/server/fake_wosarcher.py"]`. The server builds:

```
<command> run <query> --run-id <id> [--sources S] [--until U] [--profile P]
          [--attach <staging>/attachments/<name> ...]
          [--set write.<field>=<value> ...]   # global settings merged with request.writing
          [--set <request.set entries> ...]
<command> fork <parent> --from <stage> --run-id <id> [--profile P] [writing and set overrides]
<command> run <query> --run-id <id> --sources S [--until U] --profile P   # rerun
          [--attach <staging>/attachments/<entry> ...] [--set <saved override> ...]
<command> doctor --json [--profile P]
```

Writing values from global settings and the request are merged into one
dict (request wins) and emitted as `--set` before the request's own `set`
entries; `resolve()` applies overrides in order, so the later one wins
(spec: Run request precedence). Values are passed as TOML literals
(strings quoted with `json.dumps`, which is valid TOML for basic strings)
so a tone with spaces stays one value. Arguments are a list, never a shell
string.

Children inherit the server's working directory and environment, so they
resolve the same runs directory and config directory as the server.

Alternative: run stages in-process with the runner. Rejected: the design
wants one code path, cancel by signal is simpler than cooperative
cancellation across requests, and a crashed run cannot take the server
down.

### Run IDs chosen by the server

The server needs an ID before the process starts (the queue, the 201
response, the socket URL). It generates the ID with `store.new_run_id()`
and passes `--run-id` (run-orchestration; exit code 2 if `runs/<id>/`
exists).

### Rerun

`POST /api/runs/{id}/rerun` (no body) reads the original run's
`request.json` (`RunRecord`) and stages a new run of kind `rerun`: the
staged request holds `query`, `sources`, `until`, `profile` from the
record and `set` = `record.overrides` (in order), and
`runs/<id>/attachments/` is copied with `shutil.copytree` to
`runs/.queue/<new>/attachments/`. The argv passes each top-level entry of
that copy as one `--attach` (files and directories alike) and every saved
override as `--set`; global settings are not merged, because the saved
overrides already carry the writing values the original run used. The new
run is version 1 with no parent: it is a plain `wosarcher run`, not a
fork. A queued original (no `request.json` yet) answers 409; an unknown
ID answers 404. Nothing is uploaded again.

`StagedRun.kind` is `run`, `fork`, or `rerun`; `build_run_argv`,
`build_fork_argv`, and `build_rerun_argv` are three small functions.

### Staging queued runs on disk

`POST /api/runs` writes `runs/.queue/<id>/request.json` (the API request
JSON plus `created` and, for forks, `parent` and `from`) and
`runs/.queue/<id>/attachments/<name>`. `RunStore` listing ignores dot
directories. On startup the manager queues every staged directory in
`created` order. When the child exits, the staging directory is deleted
(the runner has already copied the attachments into the run directory).
This gives restart safety with no database and no extra state.

### RunManager

```python
class RunManager:
    def __init__(self, runs_dir: Path, command: list[str], limit: int, store: RunStore): ...
    async def start(self) -> None          # re-queue staged runs
    async def submit(self, staged: StagedRun) -> ActiveRun
    async def cancel(self, run_id: str) -> Literal["signalled", "dequeued"]
    def active(self, run_id: str) -> ActiveRun | None
    def queue_position(self, run_id: str) -> int | None
    async def shutdown(self) -> None
```

`ActiveRun` holds the staged request, the argv, the `asyncio.subprocess`
handle, a `deque(maxlen=20)` of stderr lines, and its `RunTail`. Scheduling
is one synchronous method on the event loop (no locks needed): `_pump()`
starts queued runs while
`len(running) < limit`; it is called after submit, after cancel of a queued
run, and when a process exits. Positions are recomputed and `run.queued` is
broadcast to each queued run's subscribers whenever the queue changes.

Process exit handling (one coroutine per child): wait for exit, run one
final tail poll, and when no terminal event was seen, append `run.failed`
(or `run.cancelled` if the server had to SIGKILL after a cancel) through
the run store's event append, which assigns the next `seq`. Then broadcast,
close subscribers, delete staging, and `_pump()`.

Cancel: `process.send_signal(SIGTERM)` and `loop.call_later(10, kill)`; the
timer is cancelled on exit.

### RunTail: polling, not inotify

Every 100 ms while its process runs, `RunTail.poll()` reads new bytes from
`events.jsonl` from a byte offset, keeps a trailing partial line for the
next poll, parses complete lines into the run-orchestration `Event` model,
and records `last_seq`; and reads new bytes of `report.md` through an
incremental UTF-8 decoder, appending them to `report_text` and producing a
`report.delta`. Both go to every subscriber's `asyncio.Queue(maxsize=1000)`;
a full queue marks the subscriber as too slow (closed with 4408).

Alternatives: `watchfiles` or inotify. Rejected: a new dependency and
platform differences for a 100 ms latency gain nobody sees.

### Gap-free replay

`subscribe(since)` runs without an `await` between its steps, so the event
loop cannot interleave a poll:

1. Register the queue; read `L = tail.last_seq` and `text = tail.report_text`.
2. Return `(L, text, queue)`.

The socket handler then reads `events.jsonl` from disk and sends events
with `since < seq <= L`, sends `report.snapshot(text)` if non-empty, then
drains the queue, which holds exactly the events after `L` and the deltas
after `text`. For runs without an `ActiveRun`, `L` is the last seq in the
file and there is no queue (spec: Stream end).

Live-only events get `seq` from the handler: the last logged seq it sent.

### report.md is written as it streams

The tailer needs the report text before the write stage ends.
run-orchestration's runner appends each `on_delta` chunk to `report.md`
and flushes it; at the end of the stage it rewrites the file with the
final rendered report (citations rendered in the chosen style). If the
final text differs from the streamed text, the tailer sees the file shrink
or change, and sends one `report.snapshot` with the final text instead of
a delta.

### Run summaries

`GET /api/runs` merges `RunStore.list_runs` (record plus status from the
last `run.*` event) with the manager's running and queued runs. A
`RunSummary` has:

| Field | Source |
|---|---|
| `run_id`, `created`, `profile`, `parent_run_id`, `version`, `fork_from` | `RunRecord` |
| `query`, `sources`, `until` | `RunRecord.request` |
| `writing` | `RunRecord.settings["write"]` parsed as `WritingOptions` (resolved values) |
| `status` | `running` or `queued` from the manager, else the store status (`done`, `failed`, `cancelled`, `interrupted`) |
| `duration_s` | `run.started` ts to the terminal `run.*` event ts of `events.jsonl`, in seconds; null while queued or running and for `interrupted` |
| `cost` | `costs.json` `total.cost` in dollars; null when the file is missing |
| `queue_position` | the manager; null unless queued |

A queued run has no record yet; its summary is built from the staged
request: `version` 1 (a fork: parent version plus one, `parent_run_id` and
`fork_from` from the staging), `writing` = global writing settings merged
with the request's `writing`, `duration_s` and `cost` null. `RunDetail` is
the summary plus `request` (the redacted `RunRecord` as stored), `costs`
(the `costs.json` document or null), and `last_seq`.

### API models

The request and response bodies are Pydantic models in `models.py`, so
`wosarcher schema` (which this change extends to include them) publishes
them for the frontend's generated types: `RunCreate` (`query`, `sources`,
`until`, `profile`, `writing: dict` subset validated against
`WritingOptions`, `set`), `ForkCreate` (`from_stage` aliased `from`,
`writing`, `set`, `profile`), `RunCreated` (`run_id`, `status`),
`RunSummary`, `RunDetail`, `ServerSettings` (`writing`, `sources`),
`ProfileInfo` (`name`, `source`, `active`), `ProviderCheck`,
`HealthReport`, and `ApiError` (`error`, `detail`). They are pure
contracts with no FastAPI import; `server/` uses them as route types.

### Global settings

`ServerSettings(writing: WritingOptions, sources: Literal["web","files","both"] = "both")`
(a model in `models.py`; `server/settings.py` loads and saves it), stored as `<config_dir>/server-settings.json`
(written to a temporary file and renamed). They apply only to runs started
by the server; CLI runs use the profile. Alternative: a new layer in
`config.resolve()`. Rejected: it would change CLI behaviour for a frontend
feature, and passing `--set` keeps the precedence visible in one place.

### Server configuration

`config.py` gains `ServerConfig(host="127.0.0.1", port=8765,
max_concurrent_runs=1, static_dir="web/dist")` as `Settings.server`. Port
8765 matches the prototype's socket URL.

### Provider health through `wosarcher doctor --json`

The server runs `<command> doctor --json [--profile P]` as a subprocess
with a 60 s timeout. This keeps health checks out of the event loop and
uses the same code the CLI prints. The output is provider-adapters'
`DoctorReport` (`providers: [ProviderHealth(block, provider, base_url,
device, status ok|failed|built-in, model, latency_ms, unload, error)]`,
`warnings`), which the doctor command already prints; the server maps it
to the `HealthReport` the UI shows (the design's health states):

```
HealthReport(profile, checks: list[ProviderCheck], warnings)
ProviderCheck(role=block, provider, url=base_url, model, device, status, latency_ms, detail)
status: failed                                  -> "down",     detail = error
        built-in                                -> "skipped",  detail = "built in, no endpoint"
        ok and unload == "no"                   -> "degraded", detail = "model cannot be unloaded"
        ok and latency_ms > 1000                -> "degraded", detail = "slow response"
        ok                                      -> "ok",       detail = ""
```

`profile` is the `profile` query parameter, else the active profile name
(the same lookup as `GET /api/profiles`). The mapping is one pure
function, `health_report(profile, doctor) -> HealthReport`, in
`server/meta.py`. A non-zero exit of the doctor because a provider failed
still prints valid JSON and is mapped; only a timeout or unparsable output
answers 502.

### Static frontend

If `static_dir` exists, `create_app` mounts `StaticFiles(directory=...,
html=True)` at `/` after the API routes, plus a 404 handler that returns
`index.html` for `GET` requests outside `/api`. API routes are registered
first, so they are never shadowed.

### Dependencies

`fastapi` and `uvicorn` are already in the design's tech stack.
`python-multipart` is required by FastAPI to parse `UploadFile` forms;
there is no standard-library alternative FastAPI accepts.

## Risks / Trade-offs

- [Polling every 100 ms] → Small CPU cost per active run. Mitigation: only
  runs with a live process are polled; the limit is usually 1.
- [Queue lost if the staging directory is deleted by hand] → Accepted; it
  is the only state and lives next to the runs.
- [Final report differs from streamed text] → One extra snapshot at the end
  of the write stage; clients replace their text.
- [Children inherit the environment, including secrets] → Required for the
  CLI to resolve the same config; secrets are still redacted in
  `request.json` and in every response.
- [`--run-id` collision] → The server generates random IDs and checks that
  neither `runs/<id>/` nor `runs/.queue/<id>/` exists before staging, so a
  collision means a bug; the child then fails with exit code 2 and the run
  is finalised as `run.failed` like any crash.

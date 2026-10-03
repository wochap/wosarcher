# Design

## Context

Before this change the package has contracts, ports, config, the HTTP
client (core-contracts), BM25 (lexical-bm25), adapters with fakes,
`build(settings, http, ledger) -> Adapters` and `wosarcher doctor`
(provider-adapters; `Adapters` has `searcher`, `fetcher`, `embedder`,
`scorers`, `planner`, `writer`, and `managed: dict[str, Managed]` whose
`release()` unloads a model), `attachments.collect` and the pure stages
`load search plan fetch chunk` (research-collection; `plan` lets an LLM
exception propagate), `prefilter score select` (passage-ranking; the
prefilter falls back from embeddings to BM25 and the score stage runs the
scorer fallback chain itself, reporting `ScoreResult.scorer` and `failed`,
and calls `on_item(QueryScores)` with display scores), and `write`
(report-writing; `Report.markdown` and `Report.warnings`, unknown
citations among them). Stages that produce items over time take `on_item`;
`write` takes `on_delta: Callable[[str], None]`. `scripts/check_architecture.py`
already allows `store` (models, config) and `runner` (models, ports,
lexical, config, http, stages, store). See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**

- One function runs, resumes, and continues forks: `Runner.run(run_id)`
  executes every unfinished stage of an existing run directory.
- The runner is readable top to bottom: a list of steps, one small function
  per stage, no framework.
- Events and artifacts follow one rule: artifact first, then `stage.done`.

**Non-Goals:**

- Running two stages at the same time (search and fetch are concurrent
  inside their stages, not across stages).
- Parallel runs inside one process; the server runs one subprocess per run.

## Decisions

### Packages instead of single modules

`runner`, `store`, and `cli` become packages. The architecture check keys
on the top-level part name, so `runner/steps.py` is still part `runner` and
`ALLOWED` needs no change.

```
src/wosarcher/
  runner/
    __init__.py   # Runner; the stage loop
    steps.py      # one async function per stage: read inputs, call stage, write artifact
    events.py     # EventLog (append via store, publish), snapshot_event()
    devices.py    # gpu_stage_device(), needs_release()
    caches.py     # CachedFetcher (wraps the Fetcher port), EmbeddingMapping (prefilter cache)
  store/
    __init__.py   # RunStore: create, fork, paths, artifacts, events, list_runs
    caches.py     # PageCache, EmbeddingCache (files only)
  cli/
    __init__.py   # typer app; profile, schema, doctor (moved unchanged from cli.py)
    run.py        # run, fork, runs commands
    progress.py   # rich Live view fed by events
```

Alternative: keep single modules. Rejected: `runner.py` would pass 500
lines and mix cancellation, caching, and stage glue.

### Stage table and order

`models.py` gains `Stage = Literal["load", "plan", "search", "fetch",
"chunk", "prefilter", "score", "select", "write"]` and `STAGES:
tuple[Stage, ...]` in that order. core-contracts names the run request
type; this change sets its fields:

```python
class RunRequest(BaseModel):      # frozen, extra="forbid"
    query: str                    # non-empty
    sources: Sources = "both"     # research-collection's Literal
    until: Stage | None = None    # the recipe: None = full report, "select" = context
    attachments: list[str] = []   # paths under attachments/, as copied
```

A fork's request is the parent's request with `until` replaced by the
fork's `--until`. `load` runs first because the planner
needs attachment outlines. Artifacts per stage:

| Stage | Artifact | Model | Empty fails the run when |
|---|---|---|---|
| load | `files.jsonl` | `Page` | sources = files |
| plan | `plan.json`, `initial.jsonl` | `Plan`, `Hit` | never (the stage returns at least `q0`; an LLM error fails the run) |
| search | `hits.jsonl` | `Hit` | sources = web |
| fetch | `pages.jsonl` | `Page` | sources = web, or sources = both and `files.jsonl` is empty |
| chunk | `chunks.jsonl` | `Chunk` | always |
| prefilter | `candidates.jsonl` | `Candidate` | always |
| score | `scores.jsonl` | `Score` | always (the stage's chain ends in `passthrough` by default) |
| select | `context.json` | `Context` | always |
| write | `report.md`, `report.json` | `Report` | always |

`files.jsonl` is separate from `pages.jsonl` so a fork from `fetch` can copy
attachment pages without fetched ones. `initial.jsonl` keeps the initial
search hits, which the search step passes as `initial` (research-collection
merges them so the main query is never searched twice); a fork from
`search` therefore needs no new initial search. `report.json` holds the structured
`Report` for `--json`; `report.md` is the readable form. Both refine the
Run directory section of docs/design.md.

### The stage loop

```python
async def run(self, run_id: str, until: Stage | None) -> RunStatus:
    record = self.store.read_record(run_id)
    done = self.store.finished_stages(run_id)
    todo = [s for s in STAGES[: index(until) + 1] if s not in done]
    self.log.emit("run.started", ...)
    for i, stage in enumerate(todo):
        if skipped(stage, record.request.sources):
            await self.finish_skipped(stage); continue
        await self.run_stage(stage)                       # timeout, empty check, artifact, stage.done
        await self.maybe_release(stage, todo[i + 1 :])    # exclusive policy
    self.store.write_costs(run_id, self.costs())
    self.log.emit("run.done", ...)
```

`run_stage` emits `stage.started`, calls `steps.<stage>(ctx)` under
`asyncio.timeout(settings.run.stage_timeouts[stage])`, checks emptiness with
the table above, writes the artifact through the store, then emits
`stage.done`. Each step function reads its inputs from earlier artifacts
through the store (not from memory), so a fork or resume needs no special
path. Steps call the stage functions with the signatures research-collection,
passage-ranking, and report-writing define: `load` calls
`attachments.collect([<run_dir>/attachments], max_bytes=settings.attach.max_bytes)`,
rewrites each `Attachment.name` to its path relative to `attachments/`
(so a source reads `notes.md`, not the run directory path), and passes
them to `stages.load.load`, emitting its `Skipped` items as warnings;
`plan` calls `stages.search.search([q0])` (skipped for sources `files`) and
`stages.plan.plan`; `search` passes `initial`; `fetch` wires `on_item` to
`page.fetched` or `page.failed` (`Skipped`); `prefilter` passes the
embedding cache mapping; `score` wires `on_item(QueryScores)` to
`passages.scored`; `write` wires `on_delta` to `report.delta` plus
`store.append_report(run_id, text)` (append and flush), then replaces
`report.md` with `Report.markdown` and writes `report.json`. Warnings a
stage returns (`Plan`, `PrefilterResult`, `Report.warnings`, `Skipped`
items) go into `stage.done.warnings`.

Failures: `RunFailed(stage, error)` stops the loop; the top of `run()`
catches it, emits `run.failed`, and returns `failed`. `CancelledError` is
caught, the release for the current GPU stage runs under
`asyncio.shield`, `run.cancelled` is emitted, and the error is re-raised.

### Fallback: the stages own their chains, the runner reports them

passage-ranking runs the prefilter fallback (embeddings → BM25) and the
score chain (`[score.provider, *score.fallback]`) inside the stages, so one
run never mixes scales. After the score stage the runner emits one
`stage.failed` per `ScoreResult.failed` entry, with `data.next` set to the
chain entry that followed it, and `stage.done.provider` set to
`ScoreResult.scorer`; for prefilter `stage.done.provider` is
`PrefilterResult.method`. The runner implements no fallback of its own.
LLM errors in `plan` and `write` propagate from the stages; the runner
turns them into `run.failed` with the stage and error text. Stage timeouts
wrap the whole stage; a timeout fails the run (per-request timeouts inside
adapters already turn a hung scorer into an exception that the chain
handles).

### Composition

The CLI calls `build.build(settings, http, ledger)` and passes the
`Adapters` to `Runner`; the runner only uses the Protocol-typed fields, so
it never imports adapters. Releasing a model is
`adapters.managed[block].release()` with block `llm`, `prefilter`, or
`score`. The runner wraps `fetcher` in `CachedFetcher`, which satisfies
the `Fetcher` Protocol. The score step passes
`adapters.scorers.get(settings.score.provider)` as the stage's `scorer`,
and the fetch step passes `concurrency=settings.fetch.concurrency or
config.DEFAULT_CONCURRENCY["firecrawl"]`.

`Runner` takes a `ports.Adapters` bundle and reads
`config.DEFAULT_CONCURRENCY`; it never imports `build`, so `ALLOWED` is
unchanged (the architecture check reads every import, including ones under
`TYPE_CHECKING`). Only `cli` and `server` call `build.build()`.

### Device policy

```python
GPU_BLOCK = {"plan": "llm", "prefilter": "prefilter", "score": "score", "write": "llm"}

def needs_release(done: Stage, remaining: list[Stage], settings) -> bool
```

`needs_release` finds the next stage in `remaining` that is a GPU stage
(its block has a `device`) and returns true only when the policy is
`exclusive`, the devices are equal, and the blocks differ. Stages skipped
by `--sources` are not in `remaining`. If the block's `release` is `none`
or `managed` has no entry for it, the runner emits nothing and continues;
`wosarcher doctor` already warns about that combination. A release error never
fails the run; it is added to the next stage's `stage.done.warnings`.

### Events

Event models live in `models.py` (they are contracts the server and
frontend read): `EventBase(seq, run_id, ts, stage)` and one subclass per
type with `type: Literal["..."]` and a typed `data` model; `Event` is the
discriminated union on `type`, read with a module-level `TypeAdapter`.
`RunStore.append_event(run_id, event_type, stage, data) -> Event` builds
the event, assigns `seq` (last logged `seq` plus 1; the store reads the
last line once per run and then keeps a counter per run ID), and appends
one line with `write` plus `flush`. Because the store assigns `seq`, the
server can append a final `run.failed` after a crashed child with the same
method. `EventLog` (runner/events.py) calls `store.append_event`, then each
listener. `report.delta` goes only to listeners, with the current last
`seq`. `snapshot_event(store, run_id)` reads `report.md` and the last
`seq`; the server uses it on reconnect.

Event data models (field names are contracts; the server and the frontend
read them through `wosarcher schema`):

| Type | `data` fields |
|---|---|
| `run.queued` | `position: int` |
| `run.started` | `query`, `profile`, `parent_run_id: str \| None`, `version: int`, `until: Stage \| None` |
| `run.done` | `until: Stage \| None`, `totals: UsageTotals` |
| `run.failed` | `stage: Stage \| None`, `error: str` |
| `run.cancelled` | `stage: Stage \| None` |
| `stage.started` | `device: str \| None`, `provider: str` |
| `stage.progress` | `done: int`, `total: int`, `failed: int` |
| `stage.done` | `count: int`, `seconds: float`, `usage: UsageTotals`, `provider: str \| None`, `skipped: bool`, `copied_from: str \| None`, `warnings: list[str]` |
| `stage.failed` | `error: str`, `next: str` (empty when none) |
| `resource.waiting`, `resource.released` | `device: str`, `released_stage: Stage` |
| `plan.ready` | `queries: list[Query]` |
| `hit.found` | `url`, `title`, `query_ids: list[str]` |
| `page.fetched` | `url`, `source_id`, `title`, `chars: int`, `cached: bool` |
| `page.failed` | `url`, `reason` |
| `passages.scored` | `query_id`, `scorer`, `scored: int`, `kept: int`, `threshold_display: float \| None`, `passages: list[KeptPassage]` |
| `report.delta`, `report.snapshot` | `text: str` |

`KeptPassage(chunk_id, source_id, title, uri, heading_path, text,
display: float | None)`. `UsageTotals(input_tokens, output_tokens,
requests, units, cost)` with `cost` in dollars (0 when no price is
configured). The envelope's `stage` is set for `stage.*`, `resource.*`
(the stage that waits), `hit.found`, `page.*`, `passages.scored`, and
`report.*`.

`stage.progress` is throttled: at most one per stage every 250 ms, plus a
final one before `stage.done`.

`passages.scored` is emitted from the score stage's `on_item(QueryScores)`,
one per query: counts, scorer, `threshold_display`, and the kept pairs with
their `display` values come from `QueryScores` (passage-ranking computes
them); the runner joins each pair with the chunk and page already loaded
for the step to add text, heading path, source ID, title, and URI.

Listeners are plain callables `Callable[[Event], None]` passed to `Runner`.
The CLI passes the rich progress view or nothing. Other processes (the
server) follow a run by tailing `events.jsonl` and `report.md`.

### Store

`RunStore(runs_dir: Path, cache_dir: Path)`. Run IDs are
`YYYYMMDD-HHMMSS-xxxxxx` (UTC time plus 6 random hex characters): they sort
by time and stay readable. `request.json` holds a `RunRecord` (models.py):

```python
class RunRecord(BaseModel):
    run_id: str
    created_at: datetime
    request: RunRequest
    profile: str
    overrides: list[str]          # all --set values, parent's first
    changes: list[str]            # overrides this fork added
    settings: dict[str, Any]      # resolved, secrets as "***"
    parent_run_id: str | None
    fork_from: Stage | None
    version: int
```

`fork(parent_id, from_stage, overrides)` checks `finished_stages`, copies
`attachments/` and the artifacts of earlier stages, writes the new
`RunRecord`, and logs one `stage.done` per copied stage with
`data.copied_from = parent_id`. The runner then resolves settings from the
saved `settings` plus the new overrides, with redacted secrets filled by
`config.restore_secrets(saved, current)`, where `current` is the
resolution of the saved profile now. Alternative: re-resolve from profile
name and overrides. Rejected: a profile edited after the run would silently
change a fork, and the spec asks for the saved configuration.

`run.runs_dir` and `run.cache_dir` always come from the current
resolution (profile, environment, `--set`), never from the saved settings:
they say where to find the parent and where to keep caches, not how the run
behaves. A fork is created in the same `runs_dir` as its parent.

All JSON and JSONL artifacts are written to `<name>.tmp` and renamed, so a
crash never leaves a partial file under the real name; the `stage.done`
rule still decides completion.

Attachments: `store.create()` copies files, directories (recursively), and
glob matches into `attachments/`, keeping relative paths under a directory
argument and adding `-2`, `-3` on name clashes. Filtering by format is the
load stage's job.

### Caches

`PageCache`: `<cache_dir>/pages/<sha256(normalised url)>.json` holding the
`Page` and `fetched_at`. `CachedFetcher.fetch` returns the cached page when
younger than the TTL, else fetches and stores. `page.fetched.cached` is set
from a flag the wrapper records per URL.

`EmbeddingCache`:
`<cache_dir>/embeddings/<model-slug>/<dim>/<sha[:2]>/<sha>.f32`, raw
little-endian float32 written with the standard library `array`. The
prefilter stage takes `cache: MutableMapping[str, list[float]]` keyed by
text SHA-256; the runner passes `EmbeddingMapping(cache, model, dim)`, a
`MutableMapping` over the files of one (model, dimension) directory. Model
and dimension come from `embedder.describe()` (provider-adapters'
`EmbedderInfo`: the model reported by the endpoint and its dimension),
called once before the prefilter stage when the method is `embeddings`; if
`describe()` fails, the step passes no cache and the stage's own fallback
applies. Alternative: one JSONL per model. Rejected: loading a large file
each run is slower than reading the few files a run needs.

### Settings and costs

`RunConfig` gains `runs_dir: Path | None = None`, `cache_dir: Path | None =
None` (both resolved to XDG defaults by `RunStore.from_settings`),
`page_cache_ttl_hours: float = 24`, and `stage_timeouts: dict[Stage, float]`
with defaults load 60, plan 180, search 120, fetch 600, chunk 60, prefilter
600, score 900, select 60, write 1800 seconds.

`UsageLedger` gains `total() -> Usage` and `rows() -> list[UsageRow]`
(provider, stage, usage, cost). Stage cost in `stage.done` is
`ledger.total()` after minus before the stage; stages never overlap, so
the difference is exact. `costs.json` = `{"stages": {<stage>:
UsageTotals}, "providers": {<provider>: UsageTotals}, "total":
UsageTotals}`; `total.cost` is the run's cost in dollars, which the server
lists per run.

### CLI

`cli/run.py` adds `run`, `fork`, and `runs` to the typer app.
`run` resolves settings first (errors exit 2 before any run directory
exists), creates the run, installs `loop.add_signal_handler` for SIGTERM
and SIGINT that cancels the runner task, and runs `Runner.run`. Writing
flags are appended after `--set` values as `write.<field>=<value>`, so they
win and are saved in `overrides`. `--run-id` lets the server choose the ID (generated with the public
`store.new_run_id()`); an existing directory exits 2.
`--json` prints a `RunOutput` model (`run_id`, `status`, `error`,
`run_dir`, `context`, `report`), defined in `models.py` and included in
`wosarcher schema`. Progress goes to stderr through `rich.live.Live` only
when stderr is a TTY.

`fork` accepts `--profile`: without it the fork uses the parent's saved
settings; with it, settings are resolved from that profile (as `run`
does) and then the parent's `overrides` and the new overrides are applied,
and the record's `profile` is the new name. This is what the frontend's
"Use cloud profile" retry sends.

`src/wosarcher/__main__.py` calls the typer app, so `python -m wosarcher`
works; the server and the eval harness start runs that way (`__main__` is
already in `ALLOWED` and may import `cli`).

`runs` calls `RunStore.list_runs`, which skips directories starting with
`.` (the server stages queued runs in `runs/.queue/<id>/`), and reads each
run's `request.json` and the last `run.*` line of its `events.jsonl`.

## Risks / Trade-offs

- [Stage signatures come from three earlier changes] → Step functions are
  the only place that knows them; each step is under 40 lines and has its
  own test with fakes.
- [Per-line flush of `events.jsonl`] → One syscall per event. Mitigation:
  `stage.progress` is throttled and `report.delta` is not logged.
- [`describe()` request] → One small extra request per run with
  embeddings. Acceptable for correctness of the cache key.
- [`report.md` grows during write, then is replaced by the rendered report]
  → A snapshot during write shows raw text with `[n]` markers; after
  `stage.done` it shows the final report. The frontend renders both.
- [Signal handlers on non-Unix] → `add_signal_handler` is Unix only; the
  tool targets Linux and macOS.

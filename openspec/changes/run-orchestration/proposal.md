# Proposal

## Why

After research-collection, passage-ranking, and report-writing, every stage
exists as a pure function, but nothing runs them end to end, saves their
output, or reports progress. The CLI, the server, the eval harness, and the
agent skill all need one code path that runs a research request, writes a
self-contained run directory, emits events, and can fork a finished run from
any stage.

## What Changes

- `runner/`: runs the stages in a fixed order as phases across all
  sub-queries, wires `on_item` and `on_delta` callbacks to events, reports
  the fallbacks the prefilter and score stages ran, turns stage errors and
  empty outputs into `run.failed`, applies per-stage timeouts, the
  `run.gpu_policy` device rule (release a model only when the next GPU stage
  uses the same `device` label), `--until`, cancellation (task cancel,
  SIGTERM, SIGINT), and writes `costs.json`.
- `store/`: `RunStore` for `runs/<id>/` (request record with redacted config,
  copied attachments, stage artifacts, append-only `events.jsonl` whose
  append assigns `seq`), a public run ID generator, listing that ignores
  dot directories, stage
  completion read from `stage.done` events, `fork` with lineage
  (`parent_run_id`, `version`), and two caches: fetched pages by URL with a
  TTL, embeddings by content SHA-256 plus model plus dimension.
- Event contracts: one Pydantic model per event type (`run.*`, `stage.*`,
  `resource.*`, `plan.ready`, `hit.found`, `page.fetched`, `page.failed`,
  `passages.scored`, `report.delta`, `report.snapshot`), plus `RunRecord`
  and `RunOutput`, all included in `wosarcher schema`.
- CLI: `wosarcher run`, `wosarcher fork`, `wosarcher runs`; rich progress on
  a TTY, `--json` for agents, `--run-id` so a caller (the server) chooses
  the ID. `cli.py` becomes a small `cli/` package.
- Settings: `run.runs_dir`, `run.cache_dir`, `run.page_cache_ttl_hours`,
  `run.stage_timeouts`; `UsageLedger.total()` and `UsageLedger.rows()`;
  `config.restore_secrets()` so a fork can reuse a redacted saved config.

## Non-goals

- No server, WebSocket, or `run.queued` emission (server-api emits
  `run.queued`; this change only defines its model).
- No run deletion, no run index database, no garbage collection of caches.
- No distributed scheduling: stage order is the only GPU scheduler.
- No new stage logic; stages are called as research-collection,
  passage-ranking, and report-writing define them.
- No eval harness (eval-replay) and no skill (agent-skill).

## Capabilities

### New Capabilities

- `run-lifecycle`: stage order, phases, fallback, failure rules, timeouts,
  GPU device policy, `--until`, cancellation, and cost totals.
- `run-store`: run directory layout, request record, attachments,
  stage completion, fork and lineage, page and embedding caches.
- `run-events`: the event envelope, every event type, sequence numbers,
  the log, live-only deltas, and report snapshots.
- `cli-run`: the `wosarcher run`, `wosarcher fork`, and `wosarcher runs`
  commands and their human and JSON output.

### Modified Capabilities

None (no specs are archived yet; earlier changes' capabilities are not
changed at requirement level).

## Impact

- New code: `src/wosarcher/runner/` (`__init__.py`, `steps.py`,
  `events.py`, `devices.py`, `caches.py`), `src/wosarcher/store/`
  (`__init__.py`, `caches.py`), `src/wosarcher/cli/` (`__init__.py`,
  `run.py`, `progress.py`), tests.
- Changed code: `models.py` (event models, `Stage`, `RunRequest` fields,
  `RunRecord`, `RunOutput`), `config.py` (`RunConfig` fields, `restore_secrets`),
  `http.py` (`UsageLedger.total`, `UsageLedger.rows`), `cli.py` moved
  into `cli/__init__.py`. Uses provider-adapters' `build.build` and
  `Adapters.managed[...].release()`, research-collection's
  `attachments.collect`, and passage-ranking's `ScoreResult`,
  `PrefilterResult`, and `QueryScores` as they are.
- Architecture: `store` and `runner` are already in `ALLOWED`; packages keep
  the same part names. `ALLOWED` is unchanged: the runner receives
  `ports.Adapters` and never imports `build`. `__main__.py` (already allowed) makes
  `python -m wosarcher` work for the server and the eval harness.
- No new dependencies (rich and typer come from core-contracts).
- docs/design.md sections implemented: GPU use, Endpoints and devices
  (`exclusive` policy), Run directory, Commands (`run`, `fork`, `runs`),
  Events, Errors and cancellation, Costs, Fallback is per stage
  (reporting only).
- docs/design.md sections changed: Run directory (adds `files.jsonl`,
  `report.json`; `runs_dir` and `cache_dir` locations), Package layout
  (`runner/`, `store/`, `cli/` packages), Events (event data fields,
  `seq` assigned by the store's event append, `report.md` written as it
  streams), Run directory (`initial.jsonl`).

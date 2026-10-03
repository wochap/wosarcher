# Tasks

## 1. Prerequisites in earlier code

- [ ] 1.1 Add `fastapi`, `uvicorn`, and `python-multipart` to `pyproject.toml` dependencies; verify `uv sync` succeeds and `uv run python -c "import fastapi, uvicorn, multipart"` exits 0
- [ ] 1.2 Add `ServerConfig(host="127.0.0.1", port=8765, max_concurrent_runs=1, static_dir="web/dist")` as `Settings.server` in `config.py`; verify `tests/test_config.py::test_server_defaults` and a test that `WOSARCHER_SERVER__MAX_CONCURRENT_RUNS=2` resolves to 2
- [ ] 1.3 Add the API models of design.md (API models: `RunCreate`, `ForkCreate`, `RunCreated`, `RunSummary`, `RunDetail`, `ServerSettings`, `ProfileInfo`, `ProviderCheck`, `HealthReport`, `ApiError`) to `models.py` and include them in `wosarcher schema`; verify round-trip tests in `tests/test_models.py`, that `ForkCreate.model_validate({"from": "write"})` works, and a test that the schema output has a definition for each

## 2. Test fixture

- [ ] 2.1 Write `tests/server/fake_wosarcher.py`: a script accepting `run`, `fork`, and `doctor --json` argv as the server builds them; it writes a valid `RunRecord` to `request.json` (query, sources, `until`, profile, `--set` values as `overrides`, `fork_from` and parent for `fork`), the argv to `argv.json`, copies each `--attach` path into `attachments/`, writes `events.jsonl` with increasing `seq`, and appends `report.md` in chunks, behaving per `FAKE_MODE` (`ok`, `slow`, `crash`, `ignore-term`) and handling SIGTERM by logging `run.cancelled`; verify `tests/server/test_fake.py` runs it once per mode and checks the log ends as expected
- [ ] 2.2 Add `tests/server/conftest.py` fixtures: temporary runs and config directories, `create_app` with the fake command, and a `TestClient`; verify the fixture test `test_app_starts` gets 200 from `GET /api/runs`

## 3. Server package and settings

- [ ] 3.1 Create `server/__init__.py` with `create_app(settings, runs_dir, config_dir, command)` and a lifespan that starts and shuts down the manager; JSON error handler producing `{"error", "detail"}` for 404, 409, and 422; verify `tests/server/test_errors.py::test_unknown_run_404` and `::test_validation_names_field` (spec: API prefix and errors)
- [ ] 3.2 Implement `server/settings.py` (`ServerSettings`, `load`, `save` with temp file and rename); verify `tests/server/test_settings.py::test_defaults_without_file` and `::test_round_trip`
- [ ] 3.3 Implement `GET/PUT /api/settings` in `server/meta.py`; verify `tests/server/test_meta.py::test_settings_persist_across_apps` and `::test_invalid_settings_unchanged` (spec: Global settings)
- [ ] 3.4 Implement `GET /api/profiles` using the config profile listing; verify `tests/server/test_meta.py::test_profiles_active_marked` with a temporary `XDG_CONFIG_HOME` (spec: Profiles)
- [ ] 3.5 Implement `health_report(profile, doctor: DoctorReport) -> HealthReport` in `server/meta.py` with the status mapping of design.md (Provider health); verify `tests/server/test_meta.py::test_health_mapping` with one `ProviderHealth` per case (failed → down, built-in → skipped, unload `no` → degraded, 1840 ms → degraded, 120 ms → ok)
- [ ] 3.6 Implement `GET /api/providers/health` running `<command> doctor --json [--profile P]` with a 60 s timeout, parsing stdout as `DoctorReport` (also when the exit code is 1) and returning `health_report(...)`; 502 on timeout or unparsable output; verify `tests/server/test_meta.py::test_health_profile_param`, `::test_health_failed_provider_still_200`, and `::test_health_failure_502` (spec: Provider health)

## 4. Run queue

- [ ] 4.1 Implement staging in `server/manager.py`: `stage_run(request, uploads) -> StagedRun` writing `runs/.queue/<id>/request.json` and base-named attachments, rejecting duplicate names; verify `tests/server/test_manager.py::test_stage_basename` and `::test_duplicate_names_rejected`
- [ ] 4.2 Implement argv building (`build_run_argv`, `build_fork_argv` with `--profile` when the fork request names one) merging global writing settings with request writing, then request `set`; verify `tests/server/test_manager.py::test_argv_precedence` (request tone over settings tone, settings words used when request has none, quoted values with spaces) and `::test_fork_argv_profile` (spec: Run request precedence, Fork a run)
- [ ] 4.3 Implement `stage_rerun(run_id) -> StagedRun` (kind `rerun`: request fields and `set` = `RunRecord.overrides` from `request.json`, `shutil.copytree` of `runs/<id>/attachments/` into the staging directory) and `build_rerun_argv` (one `--attach` per top-level entry of the copied directory, every saved override as `--set`, no global settings); verify `tests/server/test_manager.py::test_rerun_staging_copies_attachments` and `::test_rerun_argv_uses_saved_overrides` (spec: Rerun a run)
- [ ] 4.4 Implement `RunManager.submit` and `_pump` with the `max_concurrent_runs` limit and FIFO queue positions; verify `tests/server/test_queue.py::test_second_run_waits` and `::test_two_slots` using `FAKE_MODE=slow` (spec: Concurrency limit)
- [ ] 4.5 Implement process exit handling: final tail poll, append `run.failed` with exit code and the last 20 stderr lines when no terminal event, delete staging, start next; verify `tests/server/test_queue.py::test_crash_appends_run_failed` with `FAKE_MODE=crash` (spec: Process exit without a terminal event)
- [ ] 4.6 Implement `RunManager.cancel`: SIGTERM plus 10 s SIGKILL timer for running runs (append `run.cancelled` after a kill), dequeue for queued runs; make the grace period a constructor argument so tests use 0.5 s; verify `tests/server/test_queue.py::test_cancel_running`, `::test_cancel_ignores_term_killed`, `::test_cancel_queued` (spec: Cancel)
- [ ] 4.7 Implement `RunManager.start` re-queuing staged runs by `created` and `shutdown` sending SIGTERM to children; verify `tests/server/test_queue.py::test_restart_requeues_in_order` and `::test_shutdown_cancels_running` (spec: Staged queued runs, Shutdown)

## 5. Run routes

- [ ] 5.1 Implement `POST /api/runs` (multipart `request` plus `attachments`) in `server/routes.py`; verify `tests/server/test_runs.py::test_create_with_attachment` (argv recorded by the fake contains `--attach .../notes.md` and `--sources both`), `::test_missing_query_422`, `::test_path_in_filename` (spec: Create a run)
- [ ] 5.2 Implement `GET /api/runs` and `GET /api/runs/{id}` returning `RunSummary`/`RunDetail` as in design.md (Run summaries): status derivation (`queued`, `running`, `done`, `failed`, `cancelled`, `interrupted`), lineage with `fork_from`, `until`, resolved `writing`, `duration_s`, `cost`, and for the detail `request`, `costs`, `last_seq`; verify `tests/server/test_runs.py::test_status_values` (one run per status built on disk or via the fake), `::test_fork_lineage` (`parent_run_id`, `version` 2, `fork_from` `write`), `::test_summary_duration_and_cost` (run directory with `run.started` at 10:00:00, `run.done` at 10:02:05, and `costs.json` total cost 0.012 → `duration_s` 125 and `cost` 0.012), and `::test_running_duration_null` (spec: List and show runs)
- [ ] 5.3 Implement `DELETE /api/runs/{id}`; verify `tests/server/test_runs.py::test_delete_running_409`, `::test_delete_finished_204`, `::test_delete_queued` (spec: Delete a run)
- [ ] 5.4 Implement `GET /api/runs/{id}/artifacts/{name}` with the allowlist (including `report.json`, `files.jsonl`, `initial.jsonl`) and content types; verify `tests/server/test_runs.py::test_artifact_allowed` (including `report.json` as `application/json`), `::test_artifact_not_listed_404` (including an encoded `../` name), `::test_artifact_missing_404` (spec: Artifacts allowlist)
- [ ] 5.5 Implement `POST /api/runs/{id}/cancel` and `POST /api/runs/{id}/fork` (stage validation, 409 for active parents); verify `tests/server/test_runs.py::test_cancel_finished_409`, `::test_fork_write_with_tone` (fake argv has `fork <id> --from write` and `--set write.tone="critical"`), `::test_fork_active_409`, `::test_fork_unknown_stage_422` (spec: Fork a run, Cancel)
- [ ] 5.6 Implement `POST /api/runs/{id}/rerun`; verify `tests/server/test_runs.py::test_rerun_copies_attachments` (the fake's argv for the new run has `--attach` pointing at a copy of `notes.md` and the original run's overrides as `--set`, and the new run's summary has `version` 1 and no parent), `::test_rerun_unknown_404`, and `::test_rerun_queued_409` (spec: Rerun a run)

## 6. Event streaming

- [ ] 6.1 Implement `server/tail.py` `RunTail.poll()` (byte offsets, partial lines, incremental UTF-8, delta or snapshot on rewrite) and `subscribe(since)`; verify `tests/server/test_tail.py::test_partial_line_held`, `::test_multibyte_split`, `::test_rewrite_sends_snapshot`, `::test_subscriber_overflow_marked`
- [ ] 6.2 Implement `WS /api/runs/{id}/events` in `server/stream.py`: 4404 for unknown runs, replay `since < seq <= L`, snapshot, queue drain, live-only `seq`, close 1000 after a terminal event, 4408 for slow clients; verify `tests/server/test_stream.py::test_unknown_run_4404`, `::test_finished_run_replay_snapshot_close`, `::test_reconnect_since` (spec: Event socket, Replay from a sequence number, Stream end, Slow clients)
- [ ] 6.3 Verify gap-free streaming end to end: `tests/server/test_stream.py::test_live_run_no_gaps` connects during a `FAKE_MODE=slow` run, disconnects, reconnects with the last seen `seq`, and checks every logged `seq` arrives exactly once and the latest snapshot plus later deltas equals `report.md` (spec: Replay from a sequence number, Live report deltas, Live-only event sequence numbers)
- [ ] 6.4 Broadcast `run.queued` with positions and `run.cancelled` for dequeued runs to socket subscribers; verify `tests/server/test_stream.py::test_queued_position_updates` and `::test_cancel_queued_notifies` (spec: Queued runs on the socket)

## 7. Static frontend and serve command

- [ ] 7.1 Mount `static_dir` when it exists, with `index.html` fallback for non-`/api` GETs; verify `tests/server/test_static.py::test_spa_fallback`, `::test_api_not_shadowed`, `::test_no_build_404` with a temporary build directory (spec: Static frontend)
- [ ] 7.2 Add `wosarcher serve [--host] [--port]` to the typer app in the `cli/` package (`cli/serve.py`, registered in `cli/__init__.py`) calling `uvicorn.run(create_app(...), host, port, proxy_headers=True)` with the production command `[sys.executable, "-m", "wosarcher"]`; verify `tests/test_cli_serve.py::test_defaults` and `::test_port_option` by patching `uvicorn.run` and checking its arguments (spec: Serve command)

## 8. Documentation and checks

- [ ] 8.1 Update docs/design.md "Server" and "Events": routes under `/api`, `run.queued`, `report.delta`, and `report.snapshot` are live-only, global settings stored in `server-settings.json` apply to server runs, `server.*` settings, `POST /api/runs/{id}/rerun`, the artifacts allowlist, the health status mapping; update the Architecture diagram line for `server/`; verify by reading the sections against the code
- [ ] 8.2 Verify `scripts/check --full` passes and `openspec validate server-api --strict` passes

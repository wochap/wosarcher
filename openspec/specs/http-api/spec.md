# http-api Specification

## Purpose

Exposes runs, artifacts, global defaults, profiles, and provider health as a
JSON API on the same origin as the frontend, so the browser UI and remote
scripts drive the same `wosarcher run` code path as the CLI.

## Requirements

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
SHALL have `query` (required, non-empty), and these optional fields:
- `sources` (`web`, `files`, or `both`)
- `until` (a stage name)
- `profile`
- `depth` (a preset name or `custom`)
- `research`: any subset of `sub_queries`, `results_per_query`,
  `max_pages`, `passages_per_query`, `context_tokens`,
  `gap_context_tokens`, and `rounds`. Each is a positive integer,
  `context_tokens` and `gap_context_tokens` may also be the string `auto`,
  and `rounds` is at most 8.
- `writing` (any subset of the writing option fields)
- `domains`: `allow` and `block`, each optional, each a list of domain
  entries (run-config "Domain lists") that replaces the configured list
  for this run
- `set` (a list of `dotted.key=value` overrides)

An unknown `depth` SHALL be rejected with 422 that names `depth`. An
invalid domain entry SHALL be rejected with 422 that names `domains.allow`
or `domains.block` and the entry. The
response SHALL be 201 with the new `run_id` and its status (`queued` or
`running`). Attachment file names SHALL be reduced to their base name; two
attachments with the same base name SHALL be rejected with 422. A request
whose resolved sources are `files` with no attachment SHALL be rejected
with 422 `invalid_attachment` before anything is staged.

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

#### Scenario: Custom research values
- **WHEN** a client posts `request = {"query": "q", "depth": "custom", "research": {"sub_queries": 6, "max_pages": 80, "rounds": 2}}`
- **THEN** the run resolves `plan.max_sub_queries` 6, `fetch.max_pages` 80, and `research.rounds` 2, and its summary has `depth = "custom"`

#### Scenario: Unknown depth
- **WHEN** a client posts `request = {"query": "q", "depth": "huge"}`
- **THEN** the response is 422 and names `depth`

#### Scenario: Too many rounds
- **WHEN** a client posts `request = {"query": "q", "research": {"rounds": 9}}`
- **THEN** the response is 422 and names `rounds`

#### Scenario: Auto context for a custom run
- **WHEN** a client posts `request = {"query": "q", "depth": "custom", "research": {"context_tokens": "auto"}}`
- **THEN** the run resolves `select.max_context_tokens` to `auto`

#### Scenario: Gap context for a custom run
- **WHEN** a client posts `request = {"query": "q", "depth": "custom", "research": {"gap_context_tokens": "auto", "rounds": 3}}`
- **THEN** the run resolves `research.gap_context_tokens` to `auto` and `research.rounds` to 3

#### Scenario: Domain lists for one run
- **WHEN** a client posts `request = {"query": "q", "domains": {"allow": ["gob.pe"], "block": []}}`
- **THEN** the run resolves `search.allow_domains` to `["gob.pe"]` and `search.block_domains` to `[]`, whatever the profile and the global settings set

#### Scenario: Invalid domain
- **WHEN** a client posts `request = {"query": "q", "domains": {"allow": ["gob.pe/tramites"]}}`
- **THEN** the response is 422, the detail names `domains.allow` and `gob.pe/tramites`, and no run is queued

### Requirement: Run request precedence
A run started by the server SHALL resolve its configuration as the CLI does
(defaults, profile, environment). It SHALL then apply, each later layer
winning:
1. the global settings;
2. the request's depth preset;
3. the request's `sources`, `research`, `writing`, and `domains` fields;
4. the request's `set` overrides.

The global domain lists are the exception: a global `domains.allow` or
`domains.block` SHALL apply only when, at the time the run is created,
neither the run's profile nor the environment sets that list
(`search.allow_domains` or `search.block_domains`), so a profile's own list
wins over the global one. A global list that applies SHALL be recorded
with the run's overrides, so a rerun repeats it. The request's `domains`
sit in layer 3 and win over both.

The profile SHALL be read when the run process starts, so profile edits
apply without restarting the server.

#### Scenario: Request overrides global default
- **WHEN** the global settings have tone `formal` and a run request has `"writing": {"tone": "critical"}`
- **THEN** the run's resolved tone is `critical`

#### Scenario: Global default applies
- **WHEN** the global settings have words 600 and a run request has no `writing`
- **THEN** the run's resolved words is 600

#### Scenario: Preset beats global default
- **WHEN** the global settings have words 1500 and a run request has `"depth": "quick"` and no `writing`
- **THEN** the run's resolved words is 600

#### Scenario: Request writing beats preset
- **WHEN** a run request has `"depth": "deep"` and `"writing": {"words": 800}`
- **THEN** the run's resolved words is 800

#### Scenario: Standard keeps the global default
- **WHEN** the global settings have words 1500 and a run request has `"depth": "standard"`
- **THEN** the run's resolved words is 1500

#### Scenario: Global domain list applies
- **WHEN** the global settings block `pinterest.com`, the profile sets no block list, and a run request has no `domains`
- **THEN** the run's resolved `search.block_domains` is `["pinterest.com"]`

#### Scenario: Profile list wins over the global list
- **WHEN** the global settings block `pinterest.com`, the profile sets `search.block_domains = ["facebook.com"]`, and a run request has no `domains`
- **THEN** the run's resolved `search.block_domains` is `["facebook.com"]`

#### Scenario: Request list wins
- **WHEN** the profile sets `search.block_domains = ["facebook.com"]` and a run request has `"domains": {"block": []}`
- **THEN** the run's resolved `search.block_domains` is `[]`

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

### Requirement: Artifacts allowlist
`GET /api/runs/{id}/artifacts/{name}` SHALL serve only these names:
`request.json`, `files.jsonl`, `plan.json`, `initial.jsonl`, `hits.jsonl`,
`pages.jsonl`, `chunks.jsonl`, `candidates.jsonl`, `scores.jsonl`,
`research.json`, `context.json`, `select.jsonl`, `report.md`,
`report.json`, `events.jsonl`, `costs.json`. JSON files SHALL be served as
`application/json`, JSONL as `application/x-ndjson`, and Markdown as
`text/markdown`, all UTF-8. Any other name, or a listed file that does not
exist, SHALL answer 404.

#### Scenario: Allowed artifact
- **WHEN** a client requests `context.json` of a finished run
- **THEN** the response is 200 with the file content and `application/json`

#### Scenario: Structured report
- **WHEN** a client requests `report.json` of a finished run
- **THEN** the response is 200 with the report body, references, and `application/json`

#### Scenario: Select skips
- **WHEN** a client requests `select.jsonl` of a run whose select stage is done
- **THEN** the response is 200 with one select skip per line and `application/x-ndjson`

#### Scenario: Name outside the allowlist
- **WHEN** a client requests the artifact `..%2Fother%2Freport.md` or `attachments`
- **THEN** the response is 404 and no file outside the allowlist is read

#### Scenario: Research record
- **WHEN** a client requests `research.json` of a finished multi-round run
- **THEN** the response is 200 with the rounds and the stop reason as `application/json`

### Requirement: Source view
`GET /api/runs/{id}/sources/{source_id}` SHALL return one source of a run
as JSON. The server SHALL compute the response from the run's stored
artifacts only (`request.json`, `plan.json`, `files.jsonl`, `pages.jsonl`, `chunks.jsonl`,
`candidates.jsonl`, `scores.jsonl`, `select.jsonl`, `context.json`). It SHALL
read whichever of these exist, so a running run answers with its current
state. It SHALL never run a pipeline stage.

The response SHALL hold:
- the source: `source_id`, `kind` (`web` or `file`), `uri`, `title`;
- `truncated`, true when the fetch cut the page;
- the run's sub-queries (`id` and `text`, in plan order);
- `threshold`, the display threshold;
- `query_cap`, the per-sub-query kept limit (`score.top_k`);
- `source_cap`, the per-source limit (`select.max_chunks_per_source`);
- `chunks`: every stored chunk of the source, in page order.

Each chunk SHALL have:
- `chunk_id`, `position`, `heading_path`, and `text`;
- `removed_before`, the number of near-duplicate chunks the chunk stage
  removed directly before it (counted from gaps in `position`);
- `queries`: one entry per sub-query, with a `state` and, once scored,
  `display`;
- `fate`: the chunk's final fate.

The per-sub-query `state` SHALL be one of:
- `not_in_results`: a web chunk whose page that sub-query did not find;
- `prefiltered`: paired with the sub-query, but not a candidate after the
  prefilter stage;
- `pending`: a candidate with no score yet;
- `below_threshold`;
- `query_cap`;
- `other_query`: kept by another sub-query;
- `kept`.

File chunks SHALL pair with every sub-query.

The `fate` SHALL hold:
- `kind`, one of `cited`, `source_cap`, `budget`, `kept`, `query_cap`,
  `below_threshold`, `prefiltered`, `pending`;
- `query_id`, the primary sub-query: the kept pair's, else the
  best-scored pair's, else none;
- `display`;
- `rank` and `ranked`: the chunk's rank among that sub-query's pairs at or
  above the threshold, and their count;
- `kept_in_query`: how many that sub-query kept;
- `n`, the citation number, when cited;
- `tokens_needed` and `tokens_left`, for a `budget` fate.

A `query_cap` fate SHALL be reported for a chunk whose best pair was over
its sub-query's cap and that no other sub-query kept. An unknown run SHALL
answer 404 `run_not_found`. A source ID not in the run's `files.jsonl` or `pages.jsonl` SHALL answer
404 `source_not_found`.

#### Scenario: Cited chunk
- **WHEN** a client requests a finished run's source whose chunk c3 is cited as passage 14 through q1
- **THEN** c3's fate is `cited` with `n` 14 and `query_id` "q1", and its rank and `kept_in_query` come from q1's scores

#### Scenario: Query cap with a higher score
- **WHEN** chunk c5 scored 0.65 in q2, q2 kept its top 10, and c5 ranked 11th of 14 at or above 0.50
- **THEN** c5's fate is `query_cap` with `display` 0.65, `rank` 11, `ranked` 14, and the response's `query_cap` is 10

#### Scenario: Not in results versus prefiltered
- **WHEN** a web page was found by q1 and q2 only, and chunk c2 was a q1 candidate but not a q2 candidate
- **THEN** c2's q2 state is `prefiltered`, its q3 state is `not_in_results`, and its q1 state follows its q1 score

#### Scenario: Over budget
- **WHEN** chunk c7 was kept by q3 but skipped by select for the budget, needing 410 tokens with 120 left
- **THEN** c7's fate is `budget` with `tokens_needed` 410 and `tokens_left` 120

#### Scenario: Run still scoring
- **WHEN** a client requests a source of a running run whose prefilter is done and whose score stage is not
- **THEN** candidate pairs have state `pending`, the other pairs `prefiltered` or `not_in_results`, and no fate is `cited`

#### Scenario: Removed near-duplicates
- **WHEN** a page's stored chunks have positions 0, 1, and 4
- **THEN** the chunk at position 4 has `removed_before` 2

#### Scenario: Unknown source
- **WHEN** a client requests a source ID that is not in the run's `files.jsonl` or `pages.jsonl`
- **THEN** the response is 404 with `error = "source_not_found"`

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
profile, depth, and its saved overrides, including writing options) and a
copy of the original run directory's attachments, with nothing uploaded
again. The new run SHALL have version 1 and no parent run; it is not a
fork. The response SHALL be 201 with the new `run_id` and its status. An
unknown run SHALL answer 404, a run that is still queued SHALL answer 409,
and a run with sources `files` whose run directory has no attachments
SHALL answer 422 `invalid_attachment`.

#### Scenario: Rerun with attachments
- **WHEN** a client reruns a finished run that had the attachment `notes.md`
- **THEN** the response is 201, the new run's process receives a copy of `notes.md` as an attachment, and the new run's summary has `version = 1` and `parent_run_id = null`

#### Scenario: Rerun keeps the writing options
- **WHEN** the original run was started with tone `critical` and the global tone is now `formal`
- **THEN** the rerun's resolved tone is `critical`

#### Scenario: Rerun of a files run without attachments
- **WHEN** a client reruns a run with sources `files` whose `attachments/` directory is missing
- **THEN** the response is 422 with `error = "invalid_attachment"`

#### Scenario: Rerun keeps the depth
- **WHEN** a client reruns a run that used depth `deep`
- **THEN** the rerun's summary has `depth = "deep"` and its resolved `plan.max_sub_queries` is 6

### Requirement: Global settings
`GET /api/settings` SHALL return the global defaults: `writing` (all writing
option fields), `sources`, and `domains` (`allow` and `block`, each a list
of domain entries, empty by default). `PUT /api/settings` SHALL replace them after
validation and persist them in `server-settings.json` in the wosarcher
config directory, so they survive a restart. Built-in writing defaults
SHALL apply when the file does not exist.

#### Scenario: Defaults persist
- **WHEN** a client puts settings with words 800 and the server restarts
- **THEN** `GET /api/settings` returns words 800

#### Scenario: Invalid settings
- **WHEN** a client puts settings with `citation_marker = "footnote"`
- **THEN** the response is 422 and the stored settings are unchanged

#### Scenario: Domain defaults normalised
- **WHEN** a client puts settings with `domains.block = ["*.Pinterest.com"]`
- **THEN** `GET /api/settings` returns `domains.block = ["pinterest.com"]`

#### Scenario: Invalid domain default
- **WHEN** a client puts settings with `domains.allow = ["https://gob.pe/"]`
- **THEN** the response is 422 naming `domains.allow` and the entry, and the stored settings are unchanged

### Requirement: Profiles
`GET /api/profiles` SHALL return every profile with:
- its `name`;
- its `source` (`builtin` or `user`);
- whether it is `active`;
- its `description` (empty when the profile sets none);
- its resolved `context_window`, `prompt_reserve_tokens`, and
  `max_output_tokens`, so a client can show the effective context budget;
- `allow_domains` and `block_domains`: the list the profile (or the
  environment) sets, or null when it sets none, so a client can tell a
  profile's own list from the global default.

#### Scenario: Active profile marked
- **WHEN** the stored default profile is `cloud`
- **THEN** the `cloud` entry has `active = true` and every other entry `false`

#### Scenario: Descriptions
- **WHEN** a client requests `GET /api/profiles` and a user profile `nixos` sets no description
- **THEN** the `workstation` entry has `description` "One GPU fits all models; models stay loaded." and the `nixos` entry has `description` ""

#### Scenario: Limits
- **WHEN** the `workstation` profile resolves `llm.context_window = 32768`
- **THEN** its entry has `context_window = 32768`, `prompt_reserve_tokens = 2000`, and `max_output_tokens = 8192`

#### Scenario: Domain lists
- **WHEN** the user profile `nixos` sets `search.block_domains = ["facebook.com"]` and no allow list
- **THEN** its entry has `block_domains = ["facebook.com"]` and `allow_domains = null`

### Requirement: Provider health
`GET /api/providers/health` SHALL return, without sending any probe, the
provider report of the active profile, or of the profile named by the
`profile` query parameter, as JSON: the profile name, the profile's
`gpu_policy` (`shared` or `exclusive`), the warnings of the last check of
that profile, and one entry per configured provider block with `role`,
`provider`, `url`, `model`, `device`, `release` (`none`, `llama-swap`, or
`ollama`), `status`, `latency_ms`, `detail`, and `checked_at`. The entries
SHALL come from the resolved configuration of the profile, in block order,
merged with the last check result the server holds for that profile and
block.

The status SHALL be `skipped` for a built-in provider (no endpoint, no
check needed), `unchecked` for a block with no stored result, and
otherwise the stored result: `down` for a failed probe, `degraded` for a
probe that succeeded but took more than 1000 ms or whose model cannot be
unloaded although a release is configured, and `ok` otherwise.
`checked_at` SHALL be the time the stored result was taken, and null for
`unchecked` and `skipped`. A stored result whose provider, URL, or model
no longer matches the configuration SHALL be ignored. Stored results SHALL
live in the server process only and SHALL be lost when the server
restarts. No secret SHALL appear in the response. An invalid profile SHALL
answer 400 with the reason.

#### Scenario: Health of a named profile
- **WHEN** a client requests `GET /api/providers/health?profile=cloud`
- **THEN** the response lists the providers of the `cloud` profile

#### Scenario: Never checked
- **WHEN** the server has just started and a client requests `GET /api/providers/health`
- **THEN** no request reaches any provider endpoint, every block with an endpoint has `status = "unchecked"` and `checked_at = null`, and built-in blocks have `status = "skipped"`

#### Scenario: Slow provider
- **WHEN** a check found the search probe succeeding in 1840 ms and a client then requests `GET /api/providers/health`
- **THEN** no probe is sent, and the search entry has `status = "degraded"`, `latency_ms = 1840`, and the check's `checked_at`

#### Scenario: Unreachable provider
- **WHEN** a check found the score probe failing with a connection error and a client then requests `GET /api/providers/health`
- **THEN** the response is 200 and the score entry has `status = "down"` and the error as `detail`

#### Scenario: Configuration changed since the check
- **WHEN** the score block was checked with model `bge-reranker-v2-m3` and the profile now sets another model
- **THEN** the score entry is `unchecked`

#### Scenario: Policy and release
- **WHEN** the requested profile is `low-vram` (`gpu_policy = "exclusive"`, prefilter `release = "llama-swap"`)
- **THEN** the response has `gpu_policy` `exclusive` and the `prefilter` entry has `release` `llama-swap`

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

### Requirement: Provider health check
`POST /api/providers/health/check` SHALL run the `wosarcher doctor` checks
for the active profile, or for the profile named by the `profile` query
parameter, limited to the blocks listed in the optional JSON body
`{"blocks": [...]}` (every block when the body or the list is absent). It
SHALL store each checked block's result, with the time of the check, for
that profile, replace the profile's stored warnings with the check's
warnings, and answer with the same report `GET /api/providers/health`
would return afterwards. Blocks not checked SHALL keep their stored
result. An unknown block name SHALL answer 400. When the checks cannot run
(timeout or unreadable output), the response SHALL be 502 with the reason
and stored results SHALL stay unchanged.

#### Scenario: Check one block
- **WHEN** a client posts `{"blocks": ["score"]}` to `/api/providers/health/check`
- **THEN** only the score endpoint is probed, the score entry has a new `checked_at`, and the other entries keep their previous status

#### Scenario: Check all
- **WHEN** a client posts to `/api/providers/health/check` with no body
- **THEN** every block with an endpoint is probed and every such entry has a new `checked_at`

#### Scenario: Failed probe in a check
- **WHEN** the score probe fails with a connection error during a check
- **THEN** the check response is 200 and the score entry has `status = "down"`, the error as `detail`, and a new `checked_at`

#### Scenario: Unknown block
- **WHEN** a client posts `{"blocks": ["scorer"]}`
- **THEN** the response is 400 and no provider is probed

#### Scenario: Doctor timeout
- **WHEN** the doctor does not finish within its timeout
- **THEN** the response is 502 with the reason and a following `GET /api/providers/health` returns the previous results

### Requirement: Depths
`GET /api/depths` SHALL return the depth presets in the order `quick`,
`standard`, `deep`, `exhaustive`. Each entry SHALL have:
- its `name` and `description`;
- `values` with `sub_queries`, `results_per_query`, `max_pages`,
  `passages_per_query`, `context_tokens`, `gap_context_tokens`, `rounds`,
  `queries_per_round`, and `words`.

Each value SHALL be the one the preset sets, or the built-in default when
it sets none. `context_tokens` and `gap_context_tokens` SHALL each be a
positive integer or the string `auto`; with the built-in presets
`context_tokens` is `auto` and `gap_context_tokens` is 4000. The exception is `words`: it SHALL be null when the preset
does not set it (the global default applies). Run summaries from
`GET /api/runs` and `GET /api/runs/{id}` SHALL include:
- the run's `depth` (a preset name, `custom`, or null);
- `rounds_planned` (the resolved `research.rounds`);
- `rounds_ran` (from `research.done`, null until then; 1 for single-round
  runs that finished the loop);
- `stop_reason` (null for single-round runs).

#### Scenario: Standard values
- **WHEN** a client requests `GET /api/depths`
- **THEN** the `standard` entry has `sub_queries` 3, `results_per_query` 10, `max_pages` 40, `passages_per_query` 10, `context_tokens` "auto", `gap_context_tokens` 4000, `rounds` 1, `queries_per_round` 3, and `words` null

#### Scenario: Summary depth
- **WHEN** a run was started with `"depth": "quick"`
- **THEN** its summary in `GET /api/runs` has `depth = "quick"`

#### Scenario: Summary rounds
- **WHEN** a deep run stopped after round 2 with `no new sources`
- **THEN** its summary has `rounds_planned` 3, `rounds_ran` 2, and `stop_reason` "no new sources"

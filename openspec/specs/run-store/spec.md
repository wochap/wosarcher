# run-store Specification

## Purpose

Keeps every run as a self-contained directory of plain files that can be
inspected, forked, and replayed, and caches fetched pages and embeddings
across runs.

## Requirements

### Requirement: Run directory layout
Each run SHALL live in `<runs_dir>/<run_id>/` with these files, each written
by the stage named:

| File | Written by |
|---|---|
| `request.json` | run creation; `clarifications` added by the clarify pause |
| `attachments/` | run creation |
| `files.jsonl` | load |
| `plan.json`, `initial.jsonl` | plan (research); `plan.json` by expand (catalog) |
| `hits.jsonl` | search |
| `pages.jsonl` | fetch |
| `chunks.jsonl` | chunk |
| `candidates.jsonl` | prefilter |
| `scores.jsonl` | score |
| `context.json`, `select.jsonl` | select (research); `context.json` by write (catalog with a report) |
| `report.md`, `report.json` | write |
| `structure.json` | draft |
| `nodes.jsonl` | draft, expand, extract |
| `records.jsonl` | extract |
| `catalog.json` | assemble |
| `input/` | every pause: `<id>.json`, `<id>.answer.json`, `<id>.hold` (run-questions "Pause protocol") |
| `events.jsonl` | every event that is logged |
| `costs.json` | end of the run |

A research run SHALL NOT have the four catalog files, and a catalog run
SHALL NOT have `initial.jsonl`, `candidates.jsonl`, `scores.jsonl`, or
`select.jsonl`. A catalog run SHALL have `context.json`, `report.md`, and
`report.json` only when its `output` is `report` or `both`. `input/`
SHALL exist only for runs that paused. `select.jsonl` SHALL hold one
select skip per line (see context-selection "Skipped passages").
`runs_dir` SHALL default to `$XDG_DATA_HOME/wosarcher/runs`
(`~/.local/share/wosarcher/runs` when unset) and SHALL be set by
`run.runs_dir`. Run IDs SHALL sort by creation time.

#### Scenario: Files after a full run
- **WHEN** a run with sources `both` finishes
- **THEN** its directory contains every research file in the table

#### Scenario: Files after a catalog run
- **WHEN** a catalog run with `output` `table` finishes
- **THEN** its directory contains `structure.json`, `nodes.jsonl`, `records.jsonl`, `catalog.json`, `plan.json`, `hits.jsonl`, `pages.jsonl`, `chunks.jsonl`, `events.jsonl`, and `costs.json`, and no `report.md`

#### Scenario: Files after a catalog run with a report
- **WHEN** a catalog run with `output` `both` finishes
- **THEN** its directory also contains `context.json`, `report.md`, and `report.json`

#### Scenario: Run IDs sort by time
- **WHEN** two runs are created one after the other
- **THEN** the second run ID sorts after the first

#### Scenario: Fork copies the select skips
- **WHEN** a finished run is forked with `--from write`
- **THEN** the fork's directory contains the parent's `context.json` and `select.jsonl`

#### Scenario: Pause files
- **WHEN** a run paused twice and both pauses were answered
- **THEN** its `input/` holds `1.json`, `1.answer.json`, `2.json`, and `2.answer.json`

### Requirement: Request record
`request.json` SHALL hold:
- the run request (query, sources, `until`, and attachment names);
- `kind` (`research` or `catalog`; a record without it reads as
  `research`);
- for a catalog run, `structure`: the structure the run started with, or
  the one `draft` derived, written when `draft` finishes;
- the profile name;
- `use`: the entry name of each of the five blocks the run resolved;
- the depth (a preset name, `custom`, or empty; empty for a catalog run);
- the list of overrides (the user's own, not the preset's expansion),
  with each per-run entry choice as `use.<block>=<name>`;
- the resolved configuration with every secret replaced by `***`;
- the parent run ID (empty for a new run);
- the stage a fork started from;
- the version;
- the creation time;
- `form`: for a run created through `POST /api/runs`, the request as
  the client sent it (query, `kind`, `structure`, sources, `until`,
  profile, `use`, depth, `research`, `writing`, `domains`, `llm`,
  `search_language`, and `reuse_attachments`) without `set`; for a rerun,
  the original run's `form`; absent for a fork and for a run started with
  `wosarcherd run`;
- the origin: `web` (started in the browser), `api` (started with an API
  token) with the token's name, or `cli` (started with `wosarcher run`,
  `wosarcher catalog`, or `wosarcher fork` by a person or an agent).

A fork SHALL record its parent's depth and kind. A fork, rerun, or
rewrite SHALL record the origin of the request that started it, not its
parent's.

#### Scenario: Secrets redacted
- **WHEN** a run is created with a score entry that sets `api_key`
- **THEN** `request.json` contains `"api_key": "***"` for the score block and does not contain the key

#### Scenario: Entries recorded
- **WHEN** a run is created with the profile `default` (score `rerank`) and `--use score=jev-strict`
- **THEN** `request.json` has profile `default`, `use.score` `jev-strict`, the other four entries the profile chose, and the override `use.score=jev-strict`

#### Scenario: Depth recorded
- **WHEN** a run is created with depth `deep` and `--words 800`
- **THEN** `request.json` has depth `deep`, the overrides list only `write.words=800`, and the resolved configuration has `plan.max_sub_queries` 6

#### Scenario: Fork keeps depth
- **WHEN** a run with depth `quick` is forked from `write`
- **THEN** the fork's `request.json` has depth `quick`

#### Scenario: CLI origin
- **WHEN** an agent runs `wosarcher run "q"`
- **THEN** `request.json` has origin `cli` and no token name

#### Scenario: Web rerun of a CLI run
- **WHEN** a run with origin `cli` is rerun from the web UI with a browser session
- **THEN** the new run's `request.json` has origin `web`

#### Scenario: API origin
- **WHEN** a run is created through `POST /api/runs` with the API token named `ci-runner`
- **THEN** `request.json` has origin `api` and token name `ci-runner`

#### Scenario: Form recorded
- **WHEN** a client creates a run with `request = {"query": "q", "depth": "custom", "research": {"rounds": 2}, "set": ["score.api_key=\"k\""]}`
- **THEN** `request.json` has `form` with that query, depth, and research, and no `set` and no `k` in `form`

#### Scenario: Fork has no form
- **WHEN** a run is forked from `write`
- **THEN** the fork's `request.json` has no `form`

#### Scenario: Catalog recorded
- **WHEN** a catalog run is created with a structure of six seeds
- **THEN** `request.json` has `kind` `catalog`, that `structure`, an empty depth, and `form.kind` `catalog`

#### Scenario: Derived structure recorded
- **WHEN** a catalog run starts with no structure and `draft` derives one
- **THEN** after `draft`, `request.json` has the derived `structure` and `form.structure` is null

### Requirement: Attachments copied
Attachment files, directories (recursively), and glob matches SHALL be
copied into `attachments/` when the run is created, so the run does not
depend on the original paths. Two files with the same name SHALL both be
kept.

#### Scenario: Original removed
- **WHEN** an attachment is deleted after the run was created
- **THEN** forking that run from `load` still loads the attachment

### Requirement: Stage completion
A stage SHALL count as finished only when its `stage.done` event is in
`events.jsonl`. An artifact without that event SHALL be ignored.
Artifacts SHALL be written completely before `stage.done` is logged.

#### Scenario: Half-written artifact
- **WHEN** a run was killed after writing part of `scores.jsonl` but before `stage.done` for score
- **THEN** the score stage is not finished, and a fork from `score` does not copy `scores.jsonl`

### Requirement: Fork
`fork <run_id> --from <stage>` SHALL create a new run that copies
`attachments/` and the artifacts of every stage before `<stage>`, logs a
`stage.done` for each copied stage marked as copied, and continues from
`<stage>` with the parent's saved configuration plus the new overrides. The
copied `stage.done` SHALL name in `copied_from` the run that executed the
stage: the parent's own `copied_from` for that stage when the parent copied
it too, else the parent. Secrets that are redacted in the saved
configuration SHALL be taken from the current entries the parent recorded
in `use`. A recorded entry that no longer exists SHALL fail the fork
before it is created, naming the block and the entry and listing that
block's entries, unless the fork replaces that block with `--use`. A
`--use BLOCK=NAME` SHALL replace the whole saved block with the current
entry. The fork's model SHALL be its `llm.model` override, else, with
`--use llm`, that entry's `model`, else the parent's saved `llm.model`.
When the fork's model differs from the parent's saved `llm.model`, or the
fork has `--use llm`, the chosen model's values SHALL apply again below
the fork's overrides: the built-in model defaults, then the llm entry's
`models.<id>`, then the `models.<id>` of the parent's recorded profile as
its file is now (none when that profile no longer exists); they replace
the parent's saved model values, including the parent's own overrides of
them. A fork that keeps the parent's model and entry SHALL keep the
parent's saved model values. The fork SHALL record the entries it used.
Forking from a stage whose earlier stages are not all finished SHALL fail
and name the first unfinished stage.

A fork SHALL have its parent's kind. A catalog run SHALL be forked only
from `expand` or `extract`, with the copies and the continuation that
catalog-crawl "Resume and fork of a catalog run" defines; a fork from
`expand` SHALL take `--max-depth`, `--max-nodes`, and `--pages-per-node`
and record the raised limits in `structure.json` and as overrides.

#### Scenario: Rewrite only
- **WHEN** the user forks a finished run from `write` with `--set write.tone=critical`
- **THEN** the new run reuses the parent's `context.json`, makes no search, fetch, or scorer request, and writes a new report with tone `critical`

#### Scenario: Fork of an unfinished run
- **WHEN** the parent run stopped after `fetch` and the user forks from `score`
- **THEN** the fork fails with an error naming `chunk` as the first unfinished stage

#### Scenario: Fork of a fork
- **WHEN** run A ran every stage, B is a fork of A from `score`, and C is a fork of B from `write`
- **THEN** C's copied `stage.done` events for `plan` through `prefilter` have `copied_from = A`, and those for `score` and `select` have `copied_from = B`

#### Scenario: Entry gone
- **WHEN** the parent used the llm entry `sonnet`, `providers/llm/sonnet.toml` was removed, and the user forks from `write`
- **THEN** the fork fails naming `llm`, `sonnet`, and the current llm entries, and no run directory is created

#### Scenario: Entry gone, replaced
- **WHEN** the same parent is forked from `write` with `--use llm=omniroute`
- **THEN** the fork runs the write stage with the `omniroute` entry and its default model's values, and records `use.llm` `omniroute`

#### Scenario: Profile model table applies again
- **WHEN** the parent ran with profile `cloud-rerank`, whose `models."claude-sonnet-5-5"` sets `reasoning.write = "high"`, and the user forks from `write` with `--use llm=openrouter`, whose default model is `claude-sonnet-5-5`
- **THEN** the fork resolves `llm.reasoning.write` `high`

#### Scenario: Profile gone
- **WHEN** the same parent's profile `cloud-rerank` was deleted and the user forks from `write` with `--use llm=openrouter`
- **THEN** the fork resolves the model values from the `openrouter` entry alone

#### Scenario: Model change applies its values
- **WHEN** the parent ran on entry `omniroute` with model `research-smart` (`context_window` 1048576, `max_output_tokens` 131072, `reasoning.write` `low`), and the user forks from `select` with `--model qwen3-30b-a3b`, which no entry or profile lists
- **THEN** the fork resolves `llm.context_window` 32768, `llm.max_output_tokens` 8192, and `llm.reasoning.write` `none`, and keeps `use.llm` `omniroute`

#### Scenario: Model change with a limit override
- **WHEN** the same parent is forked from `select` with `--model qwen3-30b-a3b --context-window 65536`
- **THEN** the fork resolves `llm.context_window` 65536 and `llm.max_output_tokens` 8192

#### Scenario: Same model keeps saved values
- **WHEN** the parent ran with `--context-window 200000` on model `research-smart`, and the user forks from `write` with `--model research-smart --tone critical`
- **THEN** the fork resolves `llm.context_window` 200000, as the parent did

#### Scenario: Catalog model change
- **WHEN** a catalog run on model `research-smart` with `reasoning.extract` `low` from its entry is forked from `extract` with `--model qwen3-30b-a3b`
- **THEN** the fork resolves `llm.reasoning.extract` `none` and the built-in window and output limits

#### Scenario: Catalog fork keeps the kind
- **WHEN** a catalog run is forked from `extract`
- **THEN** the fork's `request.json` has `kind` `catalog` and `fork_from` `extract`, and its directory holds the parent's `nodes.jsonl` and `pages.jsonl` and no `records.jsonl`

### Requirement: Lineage
A new run SHALL have version 1 and no parent. A fork SHALL record its
`parent_run_id`, SHALL have as version the highest version among the runs
of its lineage (the root run without a parent and every run whose parent
chain reaches it) plus one, so no two runs of a lineage share a version,
and SHALL record the overrides it added over the parent.

#### Scenario: Second fork
- **WHEN** run A (version 1) is forked to B, and B is forked to C
- **THEN** B has version 2 and parent A, and C has version 3 and parent B

#### Scenario: Two rewrites of the first version
- **WHEN** run A (version 1) is forked to B (version 2), and A is forked again to D
- **THEN** D has version 3 and parent A

### Requirement: Run listing
Listing runs SHALL return every run directory under `runs_dir`, newest
first, and SHALL ignore directories whose name starts with `.` (the server
keeps its queue in `runs/.queue/`).

#### Scenario: Dot directory ignored
- **WHEN** `runs_dir` contains `.queue/` and two run directories
- **THEN** the listing contains exactly the two runs

### Requirement: Page cache
Fetched pages SHALL be cached by normalised URL in
`<cache_dir>/pages/`, where `cache_dir` defaults to
`$XDG_CACHE_HOME/wosarcher` and is set by `run.cache_dir`. A cached page
younger than `run.page_cache_ttl_hours` (default 24) SHALL be used instead
of fetching. A TTL of 0 SHALL disable the page cache.

#### Scenario: Cache hit
- **WHEN** two runs within the TTL fetch the same URL
- **THEN** the second run makes no fetch request for that URL

#### Scenario: Expired
- **WHEN** the cached page is older than the TTL
- **THEN** the page is fetched again and the cache entry replaced

### Requirement: Embedding cache
Embeddings SHALL be cached by the SHA-256 of the text, the model name
reported by the embedding endpoint, and the vector dimension. A vector SHALL be reused
only when all three match. Storing a vector whose length differs from the
cache entry's dimension SHALL fail with an error naming both dimensions,
and nothing SHALL be written.

#### Scenario: Same text, same model
- **WHEN** a chunk is embedded in one run and the same text is embedded again with the same model and dimension
- **THEN** the second embedding comes from the cache and no request is sent for it

#### Scenario: Different model
- **WHEN** the endpoint reports a different model name
- **THEN** no cached vector from the old model is used

#### Scenario: Wrong dimension
- **WHEN** a 768-dimensional vector is stored under an identity with dimension 1024
- **THEN** storing fails with an error naming 768 and 1024 and no file is written

### Requirement: Status of a live run
A run whose log has no `run.done`, `run.failed`, or `run.cancelled` SHALL
have status `queued` while the server has it staged, `waiting` while a
process holds its run lock and the log's last `input.needed` has no
matching `input.answered`, `running` while a process holds its run lock
otherwise (daemon-command "Run lock"), and `interrupted` otherwise. This
status SHALL be the same for every reader of the runs directory: the
server, and the server after a restart.

#### Scenario: Server restarts during a run
- **WHEN** the server restarts while a run process it spawned is in `fetch`
- **THEN** after the restart the run's status is `running`, not `interrupted`

#### Scenario: Run process killed
- **WHEN** a run's process is killed with SIGKILL during the `score` stage
- **THEN** the run's status is `interrupted`

#### Scenario: Direct engine run
- **WHEN** a developer's `wosarcherd run` is in its `search` stage and the server lists runs
- **THEN** the run's status is `running`

#### Scenario: CLI run seen by the server
- **WHEN** a run created over the socket is between its `search` and `fetch` stages and the server lists runs
- **THEN** the run's status is `running`

#### Scenario: Server restarts during a CLI run
- **WHEN** the server restarts while a run created over the socket is executing
- **THEN** after the restart the run's status is `running`, not `interrupted`

#### Scenario: CLI process killed
- **WHEN** a direct `wosarcherd run` process is killed with SIGKILL during the `score` stage
- **THEN** the run's status is `interrupted`

#### Scenario: Waiting run
- **WHEN** a run's process holds its lock and its log ends with `input.needed`
- **THEN** its status is `waiting`, and after `input.answered` it is `running`

#### Scenario: Killed while waiting
- **WHEN** a paused run's process is killed with SIGKILL
- **THEN** its status is `interrupted`

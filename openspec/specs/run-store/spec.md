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
| `request.json` | run creation |
| `attachments/` | run creation |
| `files.jsonl` | load |
| `plan.json`, `initial.jsonl` | plan |
| `hits.jsonl` | search |
| `pages.jsonl` | fetch |
| `chunks.jsonl` | chunk |
| `candidates.jsonl` | prefilter |
| `scores.jsonl` | score |
| `context.json` | select |
| `report.md`, `report.json` | write |
| `events.jsonl` | every event that is logged |
| `costs.json` | end of the run |

`runs_dir` SHALL default to `$XDG_DATA_HOME/wosarcher/runs`
(`~/.local/share/wosarcher/runs` when unset) and SHALL be set by
`run.runs_dir`. Run IDs SHALL sort by creation time.

#### Scenario: Files after a full run
- **WHEN** a run with sources `both` finishes
- **THEN** its directory contains every file in the table

#### Scenario: Run IDs sort by time
- **WHEN** two runs are created one after the other
- **THEN** the second run ID sorts after the first

### Requirement: Request record
`request.json` SHALL hold the run request (query, sources, `until`, and
attachment names), the profile name, the list of overrides, the resolved configuration with every secret replaced by `***`,
the parent run ID (empty for a new run), the stage a fork started from, the
version, and the creation time.

#### Scenario: Secrets redacted
- **WHEN** a run is created with `WOSARCHER_SCORE__API_KEY` set
- **THEN** `request.json` contains `"api_key": "***"` for the score block and does not contain the key

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
`stage.done` for each copied stage marked as copied from the parent, and
continues from `<stage>` with the parent's saved configuration plus the new
overrides. Secrets that are redacted in the saved configuration SHALL be
taken from the current environment and profile. Forking from a stage whose
earlier stages are not all finished SHALL fail and name the first
unfinished stage.

#### Scenario: Rewrite only
- **WHEN** the user forks a finished run from `write` with `--set write.tone=critical`
- **THEN** the new run reuses the parent's `context.json`, makes no search, fetch, or scorer request, and writes a new report with tone `critical`

#### Scenario: Fork of an unfinished run
- **WHEN** the parent run stopped after `fetch` and the user forks from `score`
- **THEN** the fork fails with an error naming `chunk` as the first unfinished stage

### Requirement: Lineage
A new run SHALL have version 1 and no parent. A fork SHALL record its
`parent_run_id` and SHALL have version parent version plus one, and SHALL
record the overrides it added over the parent.

#### Scenario: Second fork
- **WHEN** run A (version 1) is forked to B, and B is forked to C
- **THEN** B has version 2 and parent A, and C has version 3 and parent B

### Requirement: Run listing
Listing runs SHALL return every run directory under `runs_dir`, newest
first, and SHALL ignore directories whose name starts with `.` (other
programs, such as the server's queue in `runs/.queue/`, keep data there).

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
only when all three match.

#### Scenario: Same text, same model
- **WHEN** a chunk is embedded in one run and the same text is embedded again with the same model and dimension
- **THEN** the second embedding comes from the cache and no request is sent for it

#### Scenario: Different model
- **WHEN** the endpoint reports a different model name
- **THEN** no cached vector from the old model is used

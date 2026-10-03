# Spec Delta

## Purpose

Measures prefilter and scorer choices by replaying recorded runs from the
ranking stages with different settings, and keeps a recorded run that
proves the whole pipeline works end to end without live services.

## ADDED Requirements

### Requirement: Variants
The harness SHALL read named variants from a TOML file. Each variant SHALL
name the stage to fork from (`prefilter` or `score`) and a list of
`--set` overrides. A variant with any other fork stage SHALL be rejected
with an error naming the variant.

#### Scenario: Valid variant
- **WHEN** the variants file defines `bm25` with `from = "score"` and `set = ["score.provider=bm25"]`
- **THEN** replaying with `bm25` forks each run from `score` with that override

#### Scenario: Invalid stage
- **WHEN** a variant sets `from = "fetch"`
- **THEN** the harness fails before forking and names the variant and the allowed stages

### Requirement: Replay
`python -m evals.replay` SHALL fork every given recorded run with every
chosen variant through `wosarcher fork <run_id> --from <stage> --until
select --json` plus the variant's overrides, and SHALL write one result
record per (run, variant) with the parent run ID, the variant, the fork's
run ID, and its status. With `--write` the forks SHALL run through the
write stage instead. A fork that fails SHALL be recorded as failed and the
replay SHALL continue. A (run, variant) pair that already has a result
SHALL be skipped unless `--force` is given.

#### Scenario: Two variants
- **WHEN** replay runs over two recorded runs with variants `bm25` and `bm25-wide`
- **THEN** four forks are created and four result records are written

#### Scenario: Search and fetch held constant
- **WHEN** a run is replayed from `score`
- **THEN** the fork makes no search or fetch request and uses the parent's chunks

#### Scenario: Failed fork
- **WHEN** one variant's fork exits with a non-zero status (for example an invalid override)
- **THEN** that result is recorded with status `failed` and the fork's error text, and the other variants still run

### Requirement: Metrics without an LLM
`python -m evals.metrics` SHALL compute, for every result record and
without calling any model: the number of selected passages, the context
size in characters and in estimated tokens (characters divided by 4,
rounded up), the seconds of each stage the fork ran (from its `stage.done`
events), and, for each pair of variants on the same parent run, the
Jaccard overlap of their selected chunk IDs. It SHALL print a Markdown
table per variant with medians and write the full metrics as JSON.

#### Scenario: Overlap
- **WHEN** variant A selects chunks {1, 2, 3} and variant B selects {2, 3, 4} from the same parent run
- **THEN** their overlap is 0.5

#### Scenario: Stage seconds
- **WHEN** a fork from `score` logged `stage.done` for score with 1.2 seconds
- **THEN** the metrics show score 1.2 seconds and no time for the copied stages

### Requirement: Judged precision
`python -m evals.judge` SHALL, only when run explicitly, ask the configured
`llm` which selected passages of each result are relevant to the run's
query, and record precision as relevant passages divided by selected
passages. Passages SHALL be sent in a separate message from the
instructions and never through a template. An answer that cannot be
parsed SHALL record precision as missing, not zero. Judgements SHALL be
saved so a second run does not call the model again.

#### Scenario: Precision
- **WHEN** a result has 4 selected passages and the judge answers `[0, 2]`
- **THEN** its precision is 0.5

#### Scenario: Unparsable answer
- **WHEN** the judge answers text without a JSON list
- **THEN** the result's precision is missing and the judge continues with the next result

### Requirement: Recorded-run fixture
The repository SHALL contain a small recorded run directory produced by
`wosarcher run` from recorded SearXNG, Firecrawl, and LLM responses, with
every artifact of a finished run, and a script that regenerates it from
those responses. Every artifact in the fixture SHALL parse with the current
contract models.

#### Scenario: Fixture parses
- **WHEN** the test suite loads every artifact and event of the fixture run
- **THEN** each one parses with its contract model

#### Scenario: Fixture forks
- **WHEN** the fixture run is copied to a temporary runs directory and forked from `score` with `score.provider=bm25`
- **THEN** the fork finishes `select` without any network request

### Requirement: End-to-end run without live services
An automated test SHALL run `wosarcher run` with the real SearXNG,
Firecrawl, and LLM adapters against the recorded responses (no network),
with BM25 as prefilter and scorer, and SHALL check that the run finishes,
that every artifact exists, that event `seq` values have no gaps, and that
every citation in the report refers to a selected passage. No test SHALL
require a live service.

#### Scenario: Full run with recorded responses
- **WHEN** the end-to-end test runs `wosarcher run "q" --profile e2e`
- **THEN** the run ends with `run.done`, `report.md` cites only passage numbers present in `context.json`, and no request left the process

#### Scenario: Unexpected request
- **WHEN** the pipeline sends a request that has no recorded response
- **THEN** the test fails naming the URL

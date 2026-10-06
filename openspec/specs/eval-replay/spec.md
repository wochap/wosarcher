# eval-replay Specification

## Purpose

Measures prefilter and scorer choices by replaying recorded runs from the
ranking stages with different settings, and keeps a recorded run that
proves the whole pipeline works end to end without live services.

## Requirements

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

A fork that ends `done` SHALL still be recorded as `failed` when its event
log shows that it did not measure the configured ranking:
- it has a `stage.failed` event for `score`, meaning the score stage fell
  back from the configured scorer. The error is then "score ran
  <provider> instead of <configured>: <first failure>";
- its prefilter `stage.done` provider method (the part before `:`) differs
  from its resolved `prefilter.provider`. The error is then "prefilter ran
  <method> instead of <configured>".

The fork's run ID and run directory SHALL still be recorded.

#### Scenario: Two variants
- **WHEN** replay runs over two recorded runs with variants `bm25` and `bm25-wide`
- **THEN** four forks are created and four result records are written

#### Scenario: Search and fetch held constant
- **WHEN** a run is replayed from `score`
- **THEN** the fork makes no search or fetch request and uses the parent's chunks

#### Scenario: Failed fork
- **WHEN** one variant's fork exits with a non-zero status (for example an invalid override)
- **THEN** that result is recorded with status `failed` and the fork's error text, and the other variants still run

#### Scenario: Scorer fell back
- **WHEN** a variant sets `score.provider=jev` without `score.fallback=[]`, Jev answers HTTP 404, and the fork ends `done` with `bm25`
- **THEN** the result has status `failed`, the fork's run ID, and an error starting "score ran bm25 instead of jev"

#### Scenario: Prefilter fell back
- **WHEN** a variant sets `prefilter.provider=embeddings`, the embedder is unreachable, and the fork's prefilter ran `bm25`
- **THEN** the result has status `failed` and the error "prefilter ran bm25 instead of embeddings"

#### Scenario: Small-input passthrough is not a fallback
- **WHEN** every query of a fork is small-input passthrough, so the score stage reports `passthrough` with no `stage.failed`
- **THEN** the result stays `done`

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
parsed, including text without a JSON list and a list that is not valid
JSON, SHALL record precision as missing, not zero, and the judge SHALL go
on with the next result. Judgements SHALL be saved so a second run does not
call the model again.

For every result whose fork finished `write`, the judge SHALL also judge
faithfulness: each citation in the report (every `[n]` group that is not a
link, with every number it holds) pairs the sentence holding it with
passage `n`, and the `llm` is asked which pairs are supported by their
passage. Faithfulness SHALL be recorded as supported pairs divided by
pairs, and the number of pairs SHALL be recorded as `citations`. Claims and
passages SHALL be sent in a separate message from the instructions and
never through a template; only the query goes through the template. A
fork without a finished report, a report with no citation, or an
unparsable answer SHALL record faithfulness as missing, not zero, and the
judge SHALL go on. A citation number with no passage in `context.json`
SHALL be left out of the pairs.

#### Scenario: Precision
- **WHEN** a result has 4 selected passages and the judge answers `[0, 2]`
- **THEN** its precision is 0.5

#### Scenario: Unparsable answer
- **WHEN** the judge answers text without a JSON list
- **THEN** the result's precision is missing and the judge continues with the next result

#### Scenario: Malformed list
- **WHEN** the judge answers `[1, 2,]`
- **THEN** the result's precision is missing, the judge continues with the next result, and it exits 0

#### Scenario: Faithfulness
- **WHEN** a report holds the sentences "A is true [1]." and "B and C hold [2, 3]." and the judge answers `[0, 2]` for the three pairs
- **THEN** the result records `citations` 3 and faithfulness 0.67 (2 of 3)

#### Scenario: Replayed without --write
- **WHEN** a result's fork stopped at `select` and has no `report.json`
- **THEN** its precision is judged and its faithfulness is missing

#### Scenario: Report without citations
- **WHEN** a result's report cites no passage
- **THEN** its faithfulness is missing and `citations` is 0

#### Scenario: Unparsable faithfulness answer
- **WHEN** the faithfulness judge answers text without a JSON list
- **THEN** the result's faithfulness is missing, its precision is kept, and the judge continues

#### Scenario: Claims and passages as data
- **WHEN** the faithfulness judge is called
- **THEN** the system message holds only the template with the query, and the user message holds the numbered claim and passage pairs

### Requirement: Recorded-run fixture
The repository SHALL contain, tracked in version control, a small recorded
run directory produced by `wosarcher run` from recorded SearXNG, Firecrawl,
and LLM responses, with every artifact of a finished run, and a script that
regenerates it from those responses. The fixture SHALL contain no absolute
path of the machine that generated it. Every artifact in the fixture SHALL
parse with the current contract models, and the tests that use it SHALL
pass on a fresh clone without regenerating it.

#### Scenario: Fixture parses
- **WHEN** the test suite loads every artifact and event of the fixture run
- **THEN** each one parses with its contract model

#### Scenario: Fixture forks
- **WHEN** the fixture run is copied to a temporary runs directory and forked from `score` with `score.provider=bm25`
- **THEN** the fork finishes `select` without any network request

#### Scenario: Fresh clone
- **WHEN** the repository is cloned and `git ls-files tests/fixtures/runs` is run
- **THEN** every file of `tests/fixtures/runs/20260101-000000-fixture/` is listed

#### Scenario: No machine paths
- **WHEN** the fixture is regenerated in a temporary directory
- **THEN** no fixture file contains that temporary directory's path

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

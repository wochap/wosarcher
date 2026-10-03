# run-lifecycle Specification

## Purpose

Runs a research request through every pipeline stage in a fixed order,
decides when a stage has failed, falls back, releases GPU models, honours
timeouts and cancellation, and records costs.

## Requirements

### Requirement: Stage order and phases
A run SHALL execute the stages in this order: `load`, `plan`, `search`,
`fetch`, `chunk`, `prefilter`, `score`, `select`, `write`, where `plan`
first searches the main query (the initial search) and then plans, and
`search` searches the sub-queries reusing the initial search's hits. Each stage SHALL
run once over all sub-queries (a phase), never once per sub-query. A stage
SHALL start only after the previous stage is finished. The `plan` stage
SHALL include one search for the main query (the initial search) before
planning, unless the run's sources are `files`.

#### Scenario: Phases across sub-queries
- **WHEN** the plan produces three sub-queries
- **THEN** the score stage starts once, after the fetch stage has finished for all three sub-queries

#### Scenario: Initial search
- **WHEN** a run with sources `both` reaches the plan stage
- **THEN** one search for the main query runs before the planner is called, and the planner receives its result titles and snippets

### Requirement: Sources select stages
With `--sources web` the `load` stage SHALL be skipped. With `--sources
files` the initial search, `search`, and `fetch` stages SHALL be skipped.
A skipped stage SHALL still be recorded as finished with an empty output
and marked as skipped.

#### Scenario: Files only
- **WHEN** a run uses sources `files`
- **THEN** no search or fetch request is made and the `search` and `fetch` stages are recorded as skipped

### Requirement: GPU stages run one after another
A stage is a GPU stage when its provider block sets a `device` label:
`plan` and `write` use the `llm` block, `prefilter` uses the `prefilter`
block, `score` uses the `score` block. GPU stages SHALL never overlap.

#### Scenario: No overlap
- **WHEN** prefilter and score both set `device = "desktop:gpu0"`
- **THEN** the score stage sends its first request only after the prefilter stage has finished

### Requirement: Exclusive device policy
With `run.gpu_policy = "exclusive"`, after a GPU stage finishes the run
SHALL release that stage's model only when the next GPU stage that will run
uses the same `device` label and a different provider block. Before the
release the run SHALL emit `resource.waiting` for the next stage, and after
it `resource.released`. With `run.gpu_policy = "shared"` no model SHALL be
released. A block whose `release` is `none` SHALL NOT be released, and the
run SHALL continue.

#### Scenario: Same device
- **WHEN** the policy is `exclusive`, score uses device `desktop:gpu0` with `release = "llama-swap"`, and write uses device `desktop:gpu0`
- **THEN** after the score stage the reranker is released, `resource.waiting` and `resource.released` are emitted, and then the write stage starts

#### Scenario: Different devices
- **WHEN** the policy is `exclusive`, score uses device `desktop:gpu0`, and write uses device `laptop:gpu0`
- **THEN** no model is released and no resource event is emitted between score and write

#### Scenario: Same block
- **WHEN** the policy is `exclusive` and plan and write both use the `llm` block on the same device, with no GPU stage between them that runs
- **THEN** the LLM is not released between them

#### Scenario: Last GPU stage
- **WHEN** the policy is `exclusive` and the run stops after `select`
- **THEN** no release happens after the score stage

### Requirement: Per-item failures continue
A failure of one item inside a stage (one search, one page, one scorer
batch) SHALL be logged and SHALL NOT stop the stage.

#### Scenario: One page fails
- **WHEN** one of five fetched URLs fails
- **THEN** a `page.failed` event names the URL and reason, and the fetch stage finishes with four pages

### Requirement: Stage failure
A stage SHALL fail the run, with `run.failed` naming the stage and the
error text, when it raises (including an LLM error in `plan` or `write`),
when it times out, or when its output is empty where the run needs output.
The prefilter and score fallbacks happen inside those stages; the run
SHALL report them: one `stage.failed` per scorer that failed, naming the
error and the scorer that ran next, and `stage.done` naming the scorer or
prefilter method that actually ran.

Empty output that fails the run: no pages from `load` when sources are
`files`; no hits from `search` or no pages from `fetch` when sources are
`web`; no pages at all after `fetch` and `load` when sources are `both`;
no chunks; an empty context from `select`; no report text from `write`.

#### Scenario: Scorer fallback reported
- **WHEN** the configured `rerank` scorer fails and the score stage falls back to `bm25`
- **THEN** `stage.failed` is emitted naming the rerank error and `bm25` as next, the run continues, and score's `stage.done` names `bm25`

#### Scenario: Planner error
- **WHEN** the LLM raises during the plan stage
- **THEN** the run emits `run.failed` naming the `plan` stage and the error text, and no search for sub-queries is made

#### Scenario: No fallback left
- **WHEN** sources are `web` and the fetch stage returns zero pages
- **THEN** the run emits `run.failed` naming the `fetch` stage and stops

#### Scenario: Web empty but files present
- **WHEN** sources are `both`, the fetch stage returns zero pages, and attachments produced pages
- **THEN** the run continues with the attachment pages

### Requirement: Stage timeouts
Each stage SHALL have a timeout from `run.stage_timeouts`. A stage that
exceeds it SHALL be cancelled and SHALL fail the run.

#### Scenario: Score timeout
- **WHEN** the score stage exceeds its timeout
- **THEN** the stage is cancelled and the run emits `run.failed` naming `score` and the timeout

### Requirement: Stop early
A run started with `--until <stage>` SHALL stop after that stage has
finished and SHALL end with `run.done`. An unknown stage name SHALL be
rejected before the run starts.

#### Scenario: Until select
- **WHEN** a run uses `--until select`
- **THEN** `context.json` is written, no write stage runs, and the run ends with `run.done`

### Requirement: Cancellation
Cancelling the run task, or the process receiving SIGTERM or SIGINT, SHALL
cancel in-flight requests, release the current GPU stage's model when the
policy is `exclusive`, emit `run.cancelled` naming the current stage, and
exit with status 130.

#### Scenario: SIGTERM during fetch
- **WHEN** the process receives SIGTERM during the fetch stage
- **THEN** in-flight fetch requests are cancelled, `run.cancelled` with stage `fetch` is the last logged event, and the process exits with status 130

### Requirement: Cost totals
The run SHALL write `costs.json` with usage and cost per stage, per
provider, and in total, and each `stage.done` event SHALL carry that
stage's usage and cost.

#### Scenario: Costs written
- **WHEN** a run finishes after an LLM plan stage that used 100 input tokens
- **THEN** `costs.json` shows 100 input tokens for the `plan` stage and in the total

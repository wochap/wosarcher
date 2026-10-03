# Spec Delta

## Purpose

Chooses the passages the writer sees: the best kept passages, balanced
across queries and between attached files and the web, numbered for
citation, and sized to fit the writing model's context window.

## ADDED Requirements

### Requirement: Selection order
Selection SHALL consider only pairs kept by the score stage and SHALL apply,
in order: the per-source cap, then round-robin across queries until the
token budget is full. Each chunk SHALL be selected at most once.

#### Scenario: Rejected pairs ignored
- **WHEN** a pair is marked not kept by the score stage
- **THEN** its chunk is not selected through that pair

### Requirement: Per-source cap
At most `select.max_chunks_per_source` passages (default 5) SHALL be
selected from one source. When a source has more kept passages, the ones
ranked highest within their own query SHALL be kept.

#### Scenario: Long page
- **WHEN** one page has eight kept passages and `select.max_chunks_per_source = 5`
- **THEN** at most five of its passages are selected

### Requirement: Round-robin across queries
Passages SHALL be taken in rounds: each round takes the next best remaining
passage of each query, in plan order. A passage that does not fit in the
remaining budget SHALL be skipped and selection SHALL continue with the
next, until no remaining passage fits.

#### Scenario: Balanced queries
- **WHEN** `q1` has ten kept passages, `q2` has two, and the budget fits four passages
- **THEN** the selection holds two passages of `q1` and two of `q2`

### Requirement: File and web shares
When both files and web pages have kept passages, files SHALL first get
`select.file_share` of the budget (default 0.5) and web pages the rest.
Budget one side does not use SHALL then go to the remaining passages of
both sides, by the same round-robin rule.

#### Scenario: Files only
- **WHEN** a run has only file passages
- **THEN** file passages may use the whole budget

#### Scenario: Unused web share
- **WHEN** web passages use 1000 of their 5000 tokens and file passages remain
- **THEN** file passages fill the remaining budget beyond their own share

### Requirement: Token budget
The context budget SHALL be the smaller of `select.max_context_tokens`
(default 16000) and `llm.context_window` minus
`select.prompt_reserve_tokens` (default 2000) minus the output allowance,
where the output allowance is the larger of 1024 and twice the target word
count. A budget of zero or less SHALL fail with an error that names
`llm.context_window`.

#### Scenario: Small context window
- **WHEN** `llm.context_window = 8192`, `select.max_context_tokens = 16000`, and the target is 1200 words
- **THEN** the budget is 8192 - 2000 - 2400 = 3792 tokens

#### Scenario: Window too small
- **WHEN** `llm.context_window = 4000` and the target is 1200 words
- **THEN** selection fails and the error names `llm.context_window`

### Requirement: Token estimate
The token count of a passage SHALL be estimated as its character count
divided by `llm.chars_per_token` (default 3.5), times `llm.token_margin`
(default 1.1), rounded up, plus 16 tokens for its label.

#### Scenario: Estimate
- **WHEN** a passage has 700 characters with the defaults
- **THEN** its estimate is 220 + 16 = 236 tokens

### Requirement: Citation numbers
Each selected passage SHALL get a number `n`, starting at 1, in selection
order, and SHALL record its `chunk_id`, `source_id`, best query ID, text,
heading path, pdf-ingest page and block IDs, scorer, and display score. The
context SHALL list the source of every selected passage once, with its
kind, URI, title, author, and date when known.

#### Scenario: Numbers map to chunks
- **WHEN** three passages are selected
- **THEN** they have the numbers 1, 2, and 3, each with its chunk ID and source ID, and each source appears once in the context

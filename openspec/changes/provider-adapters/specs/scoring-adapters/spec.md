# Spec Delta

## Purpose

Scores (query, chunk) pairs with one of four scorers (a reranker, Jev, BM25,
or passthrough), each declaring its name and whether its scores are
calibrated, so selection can apply the right threshold.

## ADDED Requirements

### Requirement: Scorer results
Every scorer SHALL return exactly one score per input chunk, in input
order, each with the query ID, the chunk ID, a value, and the scorer's
name. Each scorer SHALL declare whether its values are calibrated: `jev`
is calibrated; `rerank`, `bm25`, and `passthrough` are not. An empty chunk
list SHALL give an empty result without any request.

#### Scenario: One score per chunk
- **WHEN** any scorer scores 5 chunks for query `q2`
- **THEN** 5 scores are returned in chunk order, each with query ID `q2` and the scorer's name

#### Scenario: Nothing to score
- **WHEN** a remote scorer is called with no chunks
- **THEN** it returns an empty list and sends no request

### Requirement: Rerank scorer
The `rerank` scorer SHALL send `POST <base_url>/rerank` with the query
text, the chunk texts as `documents`, and `model` when configured, in
batches of at most `score.batch_size`, run concurrently up to the
provider's concurrency limit. It SHALL accept results under `results` or
`data`, each with `index` and `relevance_score`, and SHALL map each index
back to its chunk within the batch. Values SHALL be the returned
`relevance_score`, unchanged. A batch whose response does not cover every
document exactly once SHALL fail the call. Usage SHALL record
`usage.prompt_tokens` or `usage.total_tokens` as input tokens and
`meta.billed_units.search_units` as units, when present.

#### Scenario: Index mapping across batches
- **WHEN** 20 chunks are scored with `batch_size = 16` and each batch's results come back sorted by score, not by index
- **THEN** every chunk gets the `relevance_score` returned for its own index

#### Scenario: Missing document
- **WHEN** a batch of 4 documents is answered with 3 results
- **THEN** the call fails with an error naming the provider

### Requirement: Jev scorer
The `jev` scorer SHALL send one `POST <base_url>/systemone` request per
chunk, with the chunk text as `state` exactly as given, `model` from
`score.model` (default `jev-latest`), and one `usefulness` question of type
`score` whose instructions name the query and whose criteria are the
four-level rubric: unrelated to the question; same topic but does not help
answer it; partially answers it or gives useful supporting facts; directly
answers it with specific facts. The question text and rubric SHALL come
from a prompt file, filled only with the query. The value SHALL be
`answers.usefulness.score`, which SHALL be between 0 and 3; a missing or
out-of-range value SHALL fail the call. Concurrency SHALL default to 64
requests. `usage.input_tokens` SHALL be recorded as input tokens.

#### Scenario: Calibrated score
- **WHEN** Jev answers `answers.usefulness.score = 2.4` for a chunk
- **THEN** that chunk's score value is 2.4 and the scorer reports itself calibrated

#### Scenario: Scraped text not templated
- **WHEN** a chunk's text contains `$query` or `{query}`
- **THEN** the request's `state` holds that text unchanged

#### Scenario: Default concurrency
- **WHEN** `score.provider = "jev"` and `score.concurrency` is not set
- **THEN** at most 64 Jev requests are in flight at once

#### Scenario: Bad answer
- **WHEN** Jev answers 200 without `answers.usefulness.score`
- **THEN** the call fails with an error naming the provider

### Requirement: BM25 scorer
The `bm25` scorer SHALL score chunks with BM25 over the given chunks only,
locally, with no request. Values SHALL be relative to the best chunk for
the query: the best chunk scores 1.0 and others their fraction of it. When
no chunk matches any query term, the first 25 chunks in input order SHALL
score 1.0 and the rest 0.0.

#### Scenario: Relative values
- **WHEN** BM25 gives raw scores 8.0, 4.0, and 0.0
- **THEN** the values are 1.0, 0.5, and 0.0

#### Scenario: No keyword overlap
- **WHEN** 30 chunks share no term with the query
- **THEN** the first 25 chunks score 1.0 and the last 5 score 0.0

### Requirement: Passthrough scorer
The `passthrough` scorer SHALL give every chunk the value 1.0 with no
request, so the order chosen by the caller (search rank, then page order)
is kept.

#### Scenario: Order kept
- **WHEN** 3 chunks are scored by passthrough
- **THEN** all three have value 1.0, in input order

### Requirement: Built-in fallbacks only
`score.fallback` SHALL accept only `bm25` and `passthrough`, because the
score block configures one remote endpoint. Any other value SHALL be
rejected when the configuration is resolved, naming the allowed values.

#### Scenario: Remote fallback rejected
- **WHEN** a profile sets `score.fallback = ["rerank"]`
- **THEN** resolution fails naming `score.fallback` and the values `bm25`, `passthrough`

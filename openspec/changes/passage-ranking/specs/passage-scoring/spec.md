# Spec Delta

## Purpose

Decides how relevant each chunk is to each query: which chunk and query
pairs are considered, how they are narrowed and scored, which survive the
threshold, and how scores are shown on one 0 to 1 scale, without ever
mixing scorers in one run.

## ADDED Requirements

### Requirement: Pairing
A web chunk SHALL be paired with every query that found its page. A file
chunk SHALL be paired with the main query and every sub-query. No other
pairs SHALL be scored.

#### Scenario: Web chunk found by two queries
- **WHEN** a page was found by `q1` and `q3` in a plan with `q0` to `q3`
- **THEN** each of its chunks is paired with `q1` and `q3` only

#### Scenario: File chunk
- **WHEN** a plan has `q0`, `q1`, and `q2` and an attachment has one chunk
- **THEN** that chunk is paired with `q0`, `q1`, and `q2` before the prefilter

### Requirement: Small-input passthrough
When the pages paired with a query total fewer than
`select.passthrough_chars` characters (default 8000), that query's pairs
SHALL skip the prefilter and the scorer and SHALL all be kept, ordered by
search rank, then page order, then chunk position, with no display score.

#### Scenario: Short pages
- **WHEN** the pages paired with `q2` total 5000 characters and `select.passthrough_chars = 8000`
- **THEN** every pair of `q2` is kept without a scorer call and is marked as passthrough

### Requirement: Prefilter
The prefilter SHALL keep, per query, the `prefilter.top_k` pairs (default
50) with the highest embedding similarity (`prefilter.provider =
"embeddings"`) or BM25 score (`"bm25"`), or SHALL keep every pair
(`"none"`). Only pairs kept by the prefilter SHALL reach the scorer. When
the embedder fails, the prefilter SHALL use BM25 for every query of the
stage and record a warning with the error. Embeddings SHALL be looked up in
and added to a cache keyed by the SHA-256 of the text when a cache is
given.

#### Scenario: Top-K per query
- **WHEN** a query has 300 paired chunks and `prefilter.top_k = 50`
- **THEN** 50 pairs of that query reach the scorer

#### Scenario: Embedder down
- **WHEN** `prefilter.provider = "embeddings"` and the embedder raises an error
- **THEN** the prefilter ranks every query with BM25, reports the method `bm25`, and records one warning with the error

#### Scenario: Cached vectors
- **WHEN** a chunk's text is already in the cache
- **THEN** the embedder is not asked for that text

### Requirement: Stage-level fallback
The score stage SHALL try the configured scorer, then each entry of
`score.fallback` in order (default `bm25`, then `passthrough`). When any
scorer call fails, the stage SHALL discard every score from that scorer and
start again with the next entry, so all scored queries in one run use the
same scorer. The result SHALL name the scorer that ran and list each failed
scorer with its error. `passthrough` SHALL never fail, so the stage always
returns scores. `score.fallback` SHALL accept only `bm25` and `passthrough`.

#### Scenario: Reranker unreachable
- **WHEN** the configured scorer `rerank` fails on its second query
- **THEN** every query is scored with `bm25`, the result names `bm25`, and lists `rerank` with its error

#### Scenario: Everything fails
- **WHEN** the configured scorer fails and BM25 is not in the fallback list
- **THEN** every pair is kept by `passthrough` and the result names `passthrough`

#### Scenario: Invalid fallback
- **WHEN** a profile sets `score.fallback = ["jev"]`
- **THEN** configuration fails and names `score.fallback` and the allowed values

### Requirement: Thresholds
A calibrated scorer SHALL keep pairs whose score is at least
`score.min_score` (default 1.5). An uncalibrated scorer SHALL keep pairs
whose score is at least `score.relative_threshold` (default 0.5) times the
best score of the same query; when the best score of a query is not
positive, only the best pair SHALL be kept. BM25 SHALL follow the BM25
ranking rule of lexical-bm25: pairs with score 0 are dropped, at most 25
pairs per query are kept, and when no pair of a query matches any query
term, the first pairs in page order are kept. Every scorer SHALL then keep
at most `score.top_k` pairs per query (default 10), best first.

#### Scenario: Calibrated threshold
- **WHEN** Jev scores three pairs 2.5, 1.5, and 1.0 with `score.min_score = 1.5`
- **THEN** the pairs scored 2.5 and 1.5 are kept

#### Scenario: Relative threshold
- **WHEN** a reranker scores a query's pairs 0.9, 0.5, and 0.4 with `score.relative_threshold = 0.5`
- **THEN** the pairs scored 0.9 and 0.5 are kept

#### Scenario: BM25 with no match
- **WHEN** BM25 is the scorer and no chunk paired with `q1` contains any term of `q1`
- **THEN** the first pairs of `q1` in page order are kept, at most `score.top_k`

#### Scenario: Negative scores
- **WHEN** a reranker scores every pair of a query below zero
- **THEN** only the best pair of that query is kept

### Requirement: Best pair per chunk
After thresholds, a chunk with more than one kept pair SHALL keep only the
pair with the highest display score (ties: the earlier query in the plan).
That pair's query ID SHALL be the chunk's best query ID; the other pairs
SHALL be marked not kept.

#### Scenario: File chunk kept once
- **WHEN** a file chunk is kept for `q0` with display 0.6 and for `q2` with display 0.8
- **THEN** only the `q2` pair is kept

### Requirement: Display score
Each scored pair SHALL have a display score from 0 to 1: the Jev score
divided by 3; the BM25 score divided by the best BM25 score of the same
query; any other scorer's score as returned, clamped to 0 to 1. Each query
SHALL also report a display threshold mapped the same way: `score.min_score`
divided by 3 for Jev, `score.relative_threshold` for BM25, and
`score.relative_threshold` times the best display score of the query for
other uncalibrated scorers. Passthrough pairs SHALL have no display score
and no threshold.

#### Scenario: Jev display
- **WHEN** Jev scores a pair 2.4 with `score.min_score = 1.5`
- **THEN** its display score is 0.8 and the query's display threshold is 0.5

#### Scenario: BM25 display
- **WHEN** BM25 scores a query's pairs 6.0 and 3.0
- **THEN** their display scores are 1.0 and 0.5

### Requirement: Per-query report
When the stage has a final scorer, it SHALL report each query to the item
callback once, with the query ID, the scorer used for it, the number of
pairs scored and kept, the display threshold, and the kept pairs. The full
result SHALL include every pair, kept or not.

#### Scenario: One report per query after fallback
- **WHEN** `rerank` fails and `bm25` succeeds for a plan with three queries
- **THEN** the item callback is called three times, each naming `bm25`

## MODIFIED Requirements

### Requirement: Prefilter
The prefilter SHALL keep, per query, the `prefilter.top_k` pairs (default
50) with the highest embedding similarity (`prefilter.provider =
"embeddings"`) or BM25 score (`"bm25"`), or SHALL keep every pair
(`"none"`). Only pairs kept by the prefilter SHALL reach the scorer. When
the embedder fails, or a vector is missing or has a different dimension
from the others, the prefilter SHALL use BM25 for every query of the stage
and record a warning with the error; it SHALL never fail the stage for
these reasons. Embeddings SHALL be looked up in and added to a cache keyed
by the SHA-256 of the text when a cache is given.

#### Scenario: Top-K per query
- **WHEN** a query has 300 paired chunks and `prefilter.top_k = 50`
- **THEN** 50 pairs of that query reach the scorer

#### Scenario: Embedder down
- **WHEN** `prefilter.provider = "embeddings"` and the embedder raises an error
- **THEN** the prefilter ranks every query with BM25, reports the method `bm25`, and records one warning with the error

#### Scenario: Cached vectors
- **WHEN** a chunk's text is already in the cache
- **THEN** the embedder is not asked for that text

#### Scenario: Dimension changes mid-stage
- **WHEN** the embedding identity has dimension 1024 and a later batch comes back with 768-dimensional vectors (a fallback URL serving another model)
- **THEN** the prefilter ranks every query with BM25, reports the method `bm25`, and records one warning naming both dimensions

### Requirement: Thresholds
A calibrated scorer SHALL keep pairs whose score is at least
`score.min_score` (default 1.5). An uncalibrated scorer SHALL keep pairs
whose mapped score is at least `score.relative_threshold` (default 0.5)
times the best mapped score of the same query; when the best mapped score
of a query is not positive, only the best pair SHALL be kept. For the
`rerank` scorer, the mapped score is the logistic sigmoid
`1 / (1 + e^-x)` of the raw score when the stage's scores are on the logit
scale, and the raw score otherwise. The scale SHALL be `score.rerank_scale`
when it is `probability` or `logit`; with `auto` (the default) it SHALL be
`logit` when any raw rerank score of the stage is below 0 or above 1, and
`probability` otherwise, so one stage never mixes scales. Raw scores SHALL
be kept unchanged in the scores artifact. BM25 SHALL follow the BM25
ranking rule of lexical-bm25: pairs with score 0 are dropped, at most 25
pairs per query are kept, and when no pair of a query matches any query
term, the first pairs in page order are kept. Every scorer SHALL then keep
at most `score.top_k` pairs per query (default 10), best first.

#### Scenario: Calibrated threshold
- **WHEN** Jev scores three pairs 2.5, 1.5, and 1.0 with `score.min_score = 1.5`
- **THEN** the pairs scored 2.5 and 1.5 are kept

#### Scenario: Relative threshold
- **WHEN** a reranker scores a query's pairs 0.9, 0.5, and 0.4 with `score.relative_threshold = 0.5` and every score of the stage is between 0 and 1
- **THEN** the pairs scored 0.9 and 0.5 are kept

#### Scenario: BM25 with no match
- **WHEN** BM25 is the scorer and no chunk paired with `q1` contains any term of `q1`
- **THEN** the first pairs of `q1` in page order are kept, at most `score.top_k`

#### Scenario: Negative logits
- **WHEN** a reranker scores a query's pairs -1.2, -1.5, and -4.0 with `score.relative_threshold = 0.5` and `score.rerank_scale = "auto"`
- **THEN** the scale is `logit`, the mapped scores are about 0.23, 0.18, and 0.018, and the pairs scored -1.2 and -1.5 are kept

#### Scenario: Large logits
- **WHEN** a reranker scores a query's pairs 6.0, 2.0, and -3.0 with `score.relative_threshold = 0.5`
- **THEN** the pairs scored 6.0 and 2.0 are kept (mapped about 0.998 and 0.88) and the pair scored -3.0 is not (about 0.047)

#### Scenario: Negative scores
- **WHEN** `score.rerank_scale = "probability"` and a reranker scores every pair of a query below zero
- **THEN** only the best pair of that query is kept

### Requirement: Display score
Each scored pair SHALL have a display score from 0 to 1: the Jev score
divided by 3; the BM25 score divided by the best BM25 score of the same
query; the `rerank` mapped score (see Thresholds) clamped to 0 to 1; any other scorer's score
as returned, clamped to 0 to 1. Each query SHALL also report a display
threshold mapped the same way: `score.min_score` divided by 3 for Jev,
`score.relative_threshold` for BM25, and `score.relative_threshold` times
the best display score of the query for other uncalibrated scorers.
Passthrough pairs SHALL have no display score and no threshold.

#### Scenario: Jev display
- **WHEN** Jev scores a pair 2.4 with `score.min_score = 1.5`
- **THEN** its display score is 0.8 and the query's display threshold is 0.5

#### Scenario: BM25 display
- **WHEN** BM25 scores a query's pairs 6.0 and 3.0
- **THEN** their display scores are 1.0 and 0.5

#### Scenario: Rerank logit display
- **WHEN** the rerank scale is `logit` and pairs of two queries score -1.0 (for `q0`) and -0.1 (for `q1`) on the same chunk
- **THEN** their display scores are about 0.27 and 0.48, so the chunk's best pair is the `q1` pair

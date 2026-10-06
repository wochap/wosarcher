# passage-scoring Specification

## Purpose

Decides how relevant each chunk is to each query: which chunk and query
pairs are considered, how they are narrowed and scored, which survive the
threshold, and how scores are shown on one 0 to 1 scale, without ever
mixing scorers in one run.

## Requirements

### Requirement: Pairing
Pairing SHALL follow `prefilter.pairing`. With `all` (the default), a web
chunk SHALL be paired with the main query and every sub-query. With
`found`, a web chunk SHALL be paired with every query that found its page.
A file chunk SHALL be paired with the main query and every sub-query under
both rules. No other pairs SHALL be scored. Any other value of
`prefilter.pairing` SHALL fail configuration naming the setting and the
two values.

#### Scenario: Web chunk pairs with every query
- **WHEN** `prefilter.pairing = "all"`, a page was found by `q1` only, and the plan has `q0` to `q3`
- **THEN** each of its chunks is paired with `q0`, `q1`, `q2`, and `q3` before the prefilter

#### Scenario: Web chunk found by two queries
- **WHEN** `prefilter.pairing = "found"` and a page was found by `q1` and `q3` in a plan with `q0` to `q3`
- **THEN** each of its chunks is paired with `q1` and `q3` only

#### Scenario: File chunk
- **WHEN** a plan has `q0`, `q1`, and `q2` and an attachment has one chunk
- **THEN** that chunk is paired with `q0`, `q1`, and `q2` before the prefilter, under either rule

#### Scenario: Invalid pairing
- **WHEN** a profile sets `prefilter.pairing = "some"`
- **THEN** configuration fails naming `prefilter.pairing` and the values `all` and `found`

### Requirement: Small-input passthrough
When the pages paired with a query total fewer than
`select.passthrough_chars` characters (default 8000), that query's pairs
SHALL skip the prefilter and the scorer. They SHALL be ordered by search
rank, then page order, then chunk position, and the first `score.top_k`
of them SHALL be kept, with no display score. The others SHALL be marked
not kept with the drop reason `query_cap`. This cap applies only to
small-input passthrough; the `passthrough` fallback scorer stays uncapped
(Requirement: Thresholds).

#### Scenario: Short pages
- **WHEN** the pages paired with `q2` total 5000 characters, they hold 4 chunks, `select.passthrough_chars = 8000`, and `score.top_k = 6`
- **THEN** every pair of `q2` is kept without a scorer call and is marked as passthrough

#### Scenario: Many small chunks
- **WHEN** the pages paired with `q0` total 7993 characters in 11 chunks and `score.top_k = 6`
- **THEN** the first 6 pairs in passthrough order are kept without a scorer call, and the other 5 are not kept with the drop reason `query_cap`

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

### Requirement: Stage-level fallback
The score stage SHALL try the configured scorer, then each entry of
`score.fallback` in order (default `bm25`, then `passthrough`). It SHALL try
no scorer that is not in that list. When any scorer call fails, the stage
SHALL discard every score from that scorer and start again with the next
entry, so all scored queries in one run use the same scorer. The result
SHALL name the scorer that ran and list each failed scorer with its error.
`passthrough` SHALL never fail. When every entry of the chain fails, the
stage SHALL fail with an error that names each scorer and its error.
`score.fallback` SHALL accept only `bm25` and `passthrough`.

#### Scenario: Reranker unreachable
- **WHEN** the configured scorer `rerank` fails on its second query
- **THEN** every query is scored with `bm25`, the result names `bm25`, and lists `rerank` with its error

#### Scenario: Everything fails
- **WHEN** the configured scorer fails and `score.fallback = ["passthrough"]`
- **THEN** every pair is kept by `passthrough` and the result names `passthrough`

#### Scenario: Invalid fallback
- **WHEN** a profile sets `score.fallback = ["jev"]`
- **THEN** configuration fails and names `score.fallback` and the allowed values

#### Scenario: No fallback
- **WHEN** `score.fallback = []` and the configured scorer `jev` fails with HTTP 404
- **THEN** the score stage fails, the run emits `run.failed` naming `score`, and the error names `jev` and the 404

#### Scenario: Default chain
- **WHEN** no source sets `score.fallback` and the configured scorer and BM25 both fail
- **THEN** every pair is kept by `passthrough`

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
term, the first pairs in page order are kept. Every scorer except
`passthrough` SHALL then keep at most `score.top_k` pairs per query
(default 10), best first. This per-query cap SHALL run before the best
pair per chunk is chosen.

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

#### Scenario: Passthrough is not capped
- **WHEN** a query's pairs are scored by `passthrough` and there are 14 of them with `score.top_k = 10`
- **THEN** all 14 pairs pass the per-query cap

### Requirement: Best pair per chunk
After thresholds and the per-query cap, a chunk with more than one kept
pair SHALL keep only the pair with the highest display score (ties: the
earlier query in the plan). That pair's query ID SHALL be the chunk's best
query ID; the other pairs SHALL be marked not kept. A pair removed by the
per-query cap SHALL take no part in this choice, so a chunk cut by the cap
of one query stays kept through another query that kept it.

#### Scenario: File chunk kept once
- **WHEN** a file chunk is kept for `q0` with display 0.6 and for `q2` with display 0.8
- **THEN** only the `q2` pair is kept

#### Scenario: Capped in its best query, kept in another
- **WHEN** a chunk scores display 0.9 for `q1` and 0.8 for `q2` with `score.top_k = 10`, `q1` has ten pairs with a higher display, and `q2` has fewer than ten
- **THEN** the `q2` pair is kept, and `q2` is the chunk's best query ID

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

### Requirement: Per-query report
When the stage has a final scorer, it SHALL report each query to the item
callback once, with the query ID, the scorer used for it, the number of
pairs scored and kept, the display threshold, and the kept pairs. The full
result SHALL include every pair, kept or not.

#### Scenario: One report per query after fallback
- **WHEN** `rerank` fails and `bm25` succeeds for a plan with three queries
- **THEN** the item callback is called three times, each naming `bm25`

### Requirement: Drop reasons
Every pair that is not kept SHALL record why, with the first rule that
dropped it: `threshold` when the scorer's keep rule (Thresholds) did not
keep it, `query_cap` when the per-query cap removed it, and `other_query`
when the chunk's best pair belongs to another query. A kept pair SHALL
record no drop reason.

#### Scenario: Below the threshold
- **WHEN** Jev scores a pair 1.0 with `score.min_score = 1.5`
- **THEN** the pair is not kept and its drop reason is `threshold`

#### Scenario: Over the query cap
- **WHEN** a query has eleven pairs above its threshold with `score.top_k = 10`
- **THEN** the lowest of them is not kept and its drop reason is `query_cap`

#### Scenario: Kept through another query
- **WHEN** a chunk is kept for `q1` with display 0.6 and for `q2` with display 0.8, both within their caps
- **THEN** the `q1` pair is not kept and its drop reason is `other_query`

### Requirement: Scoring text
With `prefilter.context = "header"` (the default), the prefilter and the
scorer SHALL rank and score each chunk by its scoring text, not its body
text alone. The scoring text SHALL be one context line, then an empty
line, then the chunk text. The context line is the page title and every
heading of the chunk's heading path, in order, joined by ` > `; empty
parts are left out. The title is cut at 120 characters and the whole
context line at 300 characters, at a word boundary when one exists. A
chunk with no title and an empty heading path SHALL have a scoring text
equal to its body text. With `prefilter.context = "body"`, the scoring
text SHALL be the body text for every chunk. Any other value SHALL fail
configuration naming `prefilter.context` and the two values. Every
ranking method of a run (embedding similarity, BM25, rerank, Jev) SHALL
use the same scoring text. The chunk artifact, the kept passages of
`passages.scored`, the selected passages, the writer's passages block,
and citations SHALL keep the body text only. Embeddings SHALL be cached by
the SHA-256 of the text that was embedded, so a scoring text and its body
text never share a cached vector.

#### Scenario: Context line
- **WHEN** a chunk of the page "Phase 3 trial of drug X" has the heading path `["Results", "Efficacy"]` and the text "Positive in 62% of cases."
- **THEN** its scoring text is "Phase 3 trial of drug X > Results > Efficacy", an empty line, then "Positive in 62% of cases."

#### Scenario: No context
- **WHEN** a chunk has an empty heading path and its page has an empty title
- **THEN** its scoring text is its body text

#### Scenario: Scorer sees the context
- **WHEN** the reranker scores a query's pairs
- **THEN** every `documents` entry of the request is that chunk's scoring text, and the scores map back to the chunk IDs

#### Scenario: Reader sees the body
- **WHEN** a chunk is selected and cited
- **THEN** its passage text in `context.json` and the writer's passages block is the body text, without the context line

#### Scenario: Long title
- **WHEN** a page title has 200 characters
- **THEN** the context line holds the first 120 characters of it, cut at a word boundary, before the heading path

#### Scenario: Body only
- **WHEN** `prefilter.context = "body"` and a chunk of the page "Phase 3 trial of drug X" has the heading path `["Results"]`
- **THEN** the embedder and the scorer receive its body text only

#### Scenario: Invalid context value
- **WHEN** a profile sets `prefilter.context = "title"`
- **THEN** configuration fails naming `prefilter.context` and the values `header` and `body`

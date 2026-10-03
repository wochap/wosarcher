# Proposal

## Why

research-collection produces chunks, often thousands per run, but the
writer can read only a few dozen passages. This change decides which ones:
it pairs chunks with the queries they can answer, narrows the pairs
cheaply, scores them with the configured scorer (falling back without
mixing score scales), and selects a cited context that fits the writer's
token budget, balanced across queries and between files and the web.

## What Changes

- Stages in `src/wosarcher/stages/`, one file each, all pure:
  - `prefilter.py`: pairs chunks with queries (web chunks with every
    query that found their page; file chunks with the main query and each
    sub-query), applies small-input passthrough (`select.passthrough_chars`),
    and keeps the top `prefilter.top_k` chunks per query by embedding
    similarity or BM25, or keeps all with `none`. Embedding failure falls
    back to BM25 for the whole stage.
  - `score.py`: scores the surviving pairs with the configured scorer;
    on failure reruns the whole stage with the next entry of
    `score.fallback` (`bm25`, then `passthrough`), so one run uses one
    scale, and records which scorer ran. Applies the calibrated absolute
    threshold (`score.min_score`) or the relative threshold
    (`score.relative_threshold`), keeps each chunk's best pair (its
    `best_query_id`), caps at `score.top_k` per query, and computes a 0 to
    1 display score and display threshold per scorer.
  - `select.py`: per-source cap, round-robin across queries best first,
    soft file and web shares with overflow, a token budget from the LLM's
    context window, and citation numbers `n` mapped to `chunk_id` and
    `source_id`. Includes the token estimate (per-model characters per
    token with a safety margin).
- Contracts: `Candidate`, `PrefilterResult`, `QueryScores`, `ScoreResult`,
  `Passage`, `Context`; `Score` gains `display` and `kept`.
- Settings: `prefilter.top_k`; `score.min_score` default 1.5 (provider-adapters
  already limits `score.fallback` to `bm25` and `passthrough`);
  `select.passthrough_chars`, `select.max_chunks_per_source`,
  `select.max_context_tokens`, `select.file_share`,
  `select.prompt_reserve_tokens`; `llm.context_window`,
  `llm.chars_per_token`, `llm.token_margin`.

## Non-goals

- No writing, prompts, or citation rendering (report-writing).
- No persistence of the embedding cache: the stage accepts a mapping; the
  runner (run-orchestration) decides where it lives and how it is keyed by
  model.
- No `/tokenize` calls to llama-server; the character ratio is the only
  token estimate.
- No mixing of scorers in one run and no per-batch fallback.
- No new adapters: the configured scorer and the embedder come from
  provider-adapters; BM25 comes from `lexical.py`.

## Capabilities

### New Capabilities

- `passage-scoring`: pairing, prefilter, small-input passthrough, scoring,
  thresholds, best pair per chunk, the stage-level fallback chain, and
  display scores.
- `context-selection`: per-source cap, round-robin across queries, file
  and web shares, the token budget and token estimate, and citation
  numbers.

### Modified Capabilities

None.

## Impact

- New code: `src/wosarcher/stages/{prefilter,score,select}.py`, tests
  under `tests/stages/`.
- Changed code: `models.py` (new contracts, `Score` fields), `config.py`
  (fields above).
- Relies on core-contracts (`Scorer` with `name` and `calibrated`,
  `Embedder`), lexical-bm25 (`bm25_scores`, `rank`), provider-adapters
  (fakes for Scorer and Embedder), research-collection (`Query`, `Page`,
  `Chunk`, `Source`, `Skipped`).
- No new dependencies; no change to `scripts/check_architecture.py`
  (`stages` may already import `lexical`).
- docs/design.md sections implemented: Scoring, Small-input passthrough,
  Select, Fallback is per stage, Citations (numbering), Tech stack
  (Tokens). Changed: Scoring (every chunk, web or file, keeps only its best
  pair; rerank threshold when no score is positive), Select (exact budget
  formula and share overflow), Frontend decisions, Scores (display rules
  stated per scorer name).

# Tasks

## 1. Contracts and settings

- [ ] 1.1 In `models.py`, add `Candidate`, `PrefilterResult`, `QueryScores`, `ScoreResult`, `Passage`, `Context`, and the `display` and `kept` fields on `Score`, exactly as in design.md (Contracts); verify round-trip tests for each in `tests/test_models.py`
- [ ] 1.2 In `config.py`, add `PrefilterConfig` (`top_k` 50, provider one of `embeddings`, `bm25`, `none`), set `ScoreConfig.min_score` to `1.5`, keep the existing `score.fallback` type from provider-adapters (`list[Literal["bm25", "passthrough"]]`; do not add a second validator), add the `SelectConfig` fields and the `LLMConfig` fields from design.md; verify tests in `tests/test_config.py` for every default, `score.fallback = ["jev"]` failing with the field name and allowed values, and `select.file_share = 1.5` failing (spec: Stage-level fallback, Invalid fallback)

## 2. Prefilter stage

- [ ] 2.1 Implement `pairs` in `stages/prefilter.py`; verify tests: a page found by `q1` and `q3` pairs its chunks with `q1` and `q3` only; a file chunk pairs with `q0`, `q1`, `q2` (spec: Pairing)
- [ ] 2.2 Implement small-input passthrough in `prefilter` (distinct paired pages' text under `passthrough_chars`); verify a test where `q2`'s pages total 5000 characters and every `q2` candidate has `passthrough=True` (spec: Small-input passthrough)
- [ ] 2.3 Implement methods `none` and `bm25` with `lexical.rank` and `lexical.bm25_scores`; verify tests: 300 paired chunks with `top_k = 50` give 50 candidates for that query; `none` keeps all (spec: Prefilter, Top-K per query)
- [ ] 2.4 Implement `embeddings` with the SHA-256 cache, one `embed` call, and cosine ranking; verify tests with the fake Embedder: cached text not requested again; embedder raising switches to `bm25` with `method == "bm25"` and one warning containing the error (spec: Prefilter, Embedder down, Cached vectors)

## 3. Score stage

- [ ] 3.1 Implement `_keep_calibrated`, `_keep_relative`, and BM25 keeping via `lexical.rank` in `stages/score.py`; verify tests with literal values: Jev 2.5/1.5/1.0 with 1.5 keeps two; rerank 0.9/0.5/0.4 with 0.5 keeps two; all negative keeps only the best; BM25 with no matching chunk keeps the first pairs in page order (spec: Thresholds)
- [ ] 3.2 Implement `_display` and the display threshold; verify tests using `pytest.approx`: Jev 2.4 gives 0.8 and threshold 0.5; BM25 6.0/3.0 gives 1.0/0.5; rerank 1.7 gives 1.0; passthrough gives None (spec: Display score)
- [ ] 3.3 Implement best pair per chunk and the per-query `top_k` cap; verify tests: a chunk kept for `q0` at 0.6 and `q2` at 0.8 keeps only `q2`; twelve kept pairs with `top_k = 10` keep ten (spec: Best pair per chunk, Thresholds)
- [ ] 3.4 Implement passthrough scoring (order by page rank, page order, position; values `len - i`; all kept; no display) and apply it to `passthrough=True` candidates always; verify a test that small-input candidates get scorer `passthrough` while other queries use the configured scorer (spec: Small-input passthrough)
- [ ] 3.5 Implement the fallback chain in `score` (configured, then `cfg.fallback`; any exception discards the step; missing or misnamed scorer counts as failure); verify tests with a fake Scorer that fails on its second query: result scorer `bm25`, `failed` lists `rerank` with the error, and no score names `rerank`; and a chain without `bm25` ends with `passthrough` keeping every pair (spec: Stage-level fallback)
- [ ] 3.6 Implement `QueryScores` and `on_item` after the final step; verify a test that a failing `rerank` then `bm25` for three queries calls `on_item` three times, each naming `bm25`, and that `ScoreResult.scores` contains rejected pairs with `kept=False` (spec: Per-query report)

## 4. Select stage

- [ ] 4.1 Implement `output_tokens`, `budget`, and `estimate_tokens` in `stages/select.py`; verify tests: window 8192 with 1200 words gives 3792; window 4000 raises naming `llm.context_window`; 700 characters with defaults estimate 220 (spec: Token budget, Token estimate)
- [ ] 4.2 Implement the per-source cap by within-query rank; verify a test where one page with eight kept passages yields at most five (spec: Per-source cap)
- [ ] 4.3 Implement `_round_robin`; verify tests: `q1` with ten and `q2` with two equal-size passages and a budget for four gives two of each; a passage too big is skipped and a smaller later one is taken (spec: Round-robin across queries)
- [ ] 4.4 Implement the two-phase file and web shares; verify tests: files-only uses the whole budget; web using 1000 of 5000 tokens lets files fill beyond their share (spec: File and web shares)
- [ ] 4.5 Implement numbering and `Context` building (passages ordered by `n`, sources once in first-use order, `used_tokens`); verify a test that three passages get 1, 2, 3 with their chunk and source IDs and that a rejected pair is never selected (spec: Citation numbers, Selection order)

## 5. Integration and docs

- [ ] 5.1 Add `tests/stages/test_ranking_flow.py`: with fakes, run `prefilter` → `score` → `select` on chunks from two web pages and one file for a three-query plan; verify every passage's chunk is kept in `ScoreResult`, numbers are 1..N, and `used_tokens <= budget_tokens`
- [ ] 5.2 Update docs/design.md: Scoring (best pair for every chunk, rerank rule when no score is positive, chain inside the score stage), Select (budget formula with `prompt_reserve_tokens` and output allowance, two-phase shares), Frontend decisions / Scores (display rules per scorer name), Tech stack / Tokens (`llm.chars_per_token`, `llm.token_margin`); verify the sections match the code
- [ ] 5.3 Verify `scripts/check --full` passes and `openspec validate passage-ranking --strict` passes

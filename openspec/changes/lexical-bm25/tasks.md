# Tasks

## 1. Tokenizer

- [ ] 1.1 Create `src/wosarcher/lexical.py` with a module docstring, the English stopword `frozenset`, and a private `_stem(token)` implementing the rules of the spec in order (`ss` kept, `ies`→`y`, `sses`/`xes`/`zes`/`ches`/`shes` drop `es`, final `s` dropped, tokens of 4 characters or fewer kept); verify `tests/test_lexical.py::test_stem_plurals` (`batteries`, `costs`, `boxes`, `churches`) and `::test_stem_non_plurals` (`class`, `glass`, `bus`, `news` unchanged) pass (spec: Light plural stemming)
- [ ] 1.2 Implement `tokenize(text: str) -> list[str]` (`\w+` over `text.lower()`, drop length-1 tokens and stopwords before stemming, then stem); verify `test_tokenize_words_and_case` (`The Battery-Life of EVs in 2024` → `battery`, `life`, `evs`, `2024`), `test_tokenize_non_latin` (`café naïve 東京`), and `test_tokenize_only_stopwords` pass (spec: Tokenization)

## 2. Scoring

- [ ] 2.1 Implement `bm25_scores(query, texts, *, k1=1.5, b=0.75) -> list[float]` as in design.md (distinct query terms, IDF `ln((N - n + 0.5)/(n + 0.5) + 1)` over the given texts, `avg_len` 1 when all texts are empty); verify `test_scores_matching_text_higher`, `test_scores_rarer_term_weighs_more` (`solar cost` against `solar panel`, `cost panel`, `cost model`), `test_scores_repeated_query_terms`, `test_scores_deterministic`, and `test_scores_empty_texts` pass (spec: BM25 scores)

## 3. Ranking

- [ ] 3.1 Implement `rank(query, texts, *, relative_threshold=0.5, max_results=25) -> list[int]` with argument validation (`ValueError` naming the argument), best-first order with ties by position, the `score > 0 and score >= threshold * best` rule, and the cap; put steps 4 and 5 of design.md "Ranking" in a private `_select(scores, relative_threshold, max_results) -> list[int]` that `rank` calls; verify `test_select_drops_weak_matches` (`_select([4.0, 2.5, 1.0], 0.5, 25)` → `[0, 1]`), `test_rank_ties_keep_input_order`, `test_rank_result_cap` (40 identical texts → positions 0 to 24), and `test_rank_invalid_threshold` pass (spec: Ranking with a relative threshold)
- [ ] 3.2 Implement the no-match fallback in `rank` (every score 0, or no query tokens → first `max_results` positions; empty texts → `[]`); verify `test_rank_nothing_matches` (30 texts, `max_results=5` → 0 to 4), `test_rank_stopword_only_query` (`what is it`, 3 texts → 0, 1, 2), and `test_rank_no_texts` pass (spec: No-match fallback)
- [ ] 3.3 Verify `lexical.py` imports only the standard library (`re`, `math`, `collections`, `collections.abc`) and stays under about 120 lines; `scripts/check` reports `architecture: ok` (spec: Pure and local)

## 4. Documentation and gate

- [ ] 4.1 Update docs/design.md, Scoring, BM25 paragraph: name the three functions (`tokenize`, `bm25_scores`, `rank`), the defaults (relative threshold 0.5, at most 25 results), and the fallback as "the first texts in the order given (callers pass chunks in search-rank, then page order)"; verify the paragraph matches `lexical.py`
- [ ] 4.2 Verify `scripts/check --full` passes and `openspec validate lexical-bm25 --strict` passes

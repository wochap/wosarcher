# Proposal

## Why

BM25 is the ranking that always works: no GPU, no API, no model. It is the
scorer on machines without a model, the prefilter when no embedding model is
configured, and the fallback when the configured scorer fails. Every later
ranking change (provider-adapters' `bm25` scorer, passage-ranking's
prefilter and fallback chain) needs one small, deterministic, tested
implementation to build on.

## What Changes

- New pure module `src/wosarcher/lexical.py` (no I/O, no dependencies
  beyond the standard library):
  - a tokenizer: Unicode word tokens, lowercased, English stopwords and
    one-character tokens removed, light plural stemming;
  - BM25 scoring of a list of texts against one query (k1 = 1.5, b = 0.75,
    IDF computed over the given texts);
  - a ranking function: best first, ties by input position, relative
    threshold (default 0.5 of the best score), maximum results (default
    25), and an opening-texts fallback when no text matches any query term.
- Unit tests for the tokenizer, the scores, and the ranking rules.
- docs/design.md, Scoring: the BM25 paragraph states the exact fallback
  (the first texts in the order given) and the defaults.

## Non-goals

- No `Scorer` adapter and no prefilter stage. The `bm25` scorer that wraps
  this module is part of provider-adapters; the prefilter and the
  fallback chain are part of passage-ranking.
- No chunking. The module ranks texts it is given.
- No languages other than English for stopwords and stemming; other
  languages still work through plain word matching.
- No index persistence or caching; scoring is fast enough per call.

## Capabilities

### New Capabilities

- `bm25-ranking`: keyword ranking of texts for a query: tokenization,
  BM25 scores, relative threshold, result cap, and the no-match fallback.

### Modified Capabilities

None.

## Impact

- New code: `src/wosarcher/lexical.py`, `tests/test_lexical.py`.
- `lexical` is already listed as pure in `scripts/check_architecture.py`
  (`ALLOWED["lexical"] = {"models"}`); this change imports nothing from
  the package, so no change to `ALLOWED`.
- No new dependencies.
- docs/design.md sections implemented: Scoring (the BM25 paragraph and the
  `bm25` threshold rule), Package layout (`lexical.py`). Changed: Scoring,
  BM25 paragraph (exact fallback and defaults).

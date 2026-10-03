# Design

## Context

core-contracts provides the package, the contracts, and the architecture
check, which already lists `lexical` as a pure part that may import only
`models`. Nothing ranks text yet. See proposal.md for why BM25 comes first.
The reference is gpt-researcher's `gpt_researcher/context/lexical.py`
(v3.7.0-fork), which measured 51% relevant passages kept against 46% for
embeddings at about 20 ms per sub-query; this design keeps its behaviour
and drops its LangChain coupling.

## Goals / Non-Goals

**Goals:**

- One module of about 100 lines, readable top to bottom, with three public
  functions and no classes.
- Works on plain strings, so the scorer adapter, the prefilter stage, and
  eval scripts can all call it without converting types.

**Non-Goals:**

- Speed beyond "fast enough": no inverted index, no numpy.
- Configurable k1 and b through settings. They are keyword arguments with
  defaults; no profile exposes them.

## Decisions

### Public API: three functions over strings

```python
def tokenize(text: str) -> list[str]: ...

def bm25_scores(query: str, texts: Sequence[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]: ...

def rank(query: str, texts: Sequence[str], *, relative_threshold: float = 0.5, max_results: int = 25) -> list[int]: ...
```

`rank` returns positions, not texts, so callers keep their own objects
(chunks with IDs) and index into them. `bm25_scores` is public because the
`bm25` scorer (provider-adapters) needs the raw scores to report them, and
`rank` because the prefilter (passage-ranking) needs the kept positions.

Alternative: a class holding the tokenized corpus for reuse across queries.
Rejected: the IDF is per query's own texts (design.md, Scoring), so there is
nothing to share between calls, and a class adds state to a pure module.

### Tokenizer

- Regex `\w+` (Unicode by default in Python 3) over `text.lower()`.
  `str.lower` rather than `casefold`, so `ß` stays `ß` and the result is
  predictable to a reader.
- Drop tokens of length 1 and tokens in a module-level `frozenset` of
  English stopwords (the classic ~120-word list). A frozen constant is data,
  not a global registry.
- Then stem with the rules in the spec (Light plural stemming), one small
  function with early returns.

The stopword list and the stemming rules are what gpt-researcher uses; they
are written fresh here from the spec.

### Scoring

Standard Okapi BM25 with the "+1" IDF variant so IDF is never negative
(a term in every text still counts a little, instead of pushing scores
below zero):

```
idf(t)   = ln((N - n_t + 0.5) / (n_t + 0.5) + 1)
score(d) = sum over distinct query terms t in d of
           idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg_len))
```

`len(d)` is the number of tokens after stopword removal. When every text
is empty after tokenization, `avg_len` is taken as 1 so there is no
division by zero (every score is then 0). Each text is tokenized once into
a `collections.Counter`.

### Ranking

1. Validate `relative_threshold` in [0, 1] and `max_results >= 1`; raise
   `ValueError` naming the argument.
2. Empty `texts` → `[]`.
3. Score; `best = max(scores)`.
4. If `best == 0` → `list(range(min(max_results, len(texts))))`
   (no-match fallback).
5. Otherwise sort positions by `(-score, position)`, keep those with
   `score > 0 and score >= relative_threshold * best`, cut to
   `max_results`.

Steps 4 and 5 live in a private `_select(scores, relative_threshold,
max_results)`, so the threshold rule can be tested with literal scores.
Floats are compared directly; scores come from the same arithmetic, so
equal inputs give bit-identical scores and ties are stable.

### Tests

`tests/test_lexical.py`, one test per spec scenario, with plain string
fixtures. No fakes or I/O are needed. BM25 behaviour is fixed by this spec
and unlikely to change, which is why unit tests (rather than only
end-to-end tests) are worth keeping here.

## Risks / Trade-offs

- [Light stemming misses irregular plurals and over-strips words like
  `analysis` → `analysi`] → Both query and texts are stemmed the same way,
  so matches still line up; the stemmer only needs to be consistent.
- [English-only stopwords] → Other languages keep their stopwords, which
  only adds weak, low-IDF matches; ranking still works.
- [IDF over few texts is noisy] → The relative threshold and the
  downstream scorer absorb it; with one text every match scores the same
  relative value (1.0), which is the right answer for one candidate.

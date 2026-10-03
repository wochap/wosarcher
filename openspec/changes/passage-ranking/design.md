# Design

## Context

Before this change: `Query`, `Plan`, `Page`, `Chunk`, `Source`, `Skipped`
(research-collection); `Scorer` with `name` and `calibrated`, `Embedder`,
`Score(query_id, chunk_id, value, scorer)`, `ScoreConfig` with
`min_score`, `relative_threshold`, `top_k`, `fallback` (core-contracts);
`lexical.bm25_scores(query, texts)` and `lexical.rank(query, texts, *,
relative_threshold, max_results)` (lexical-bm25); the rerank, jev, bm25
scorer and embeddings adapters with fakes (provider-adapters). See
proposal.md for scope.

## Goals / Non-Goals

**Goals:**

- Three stage files, each readable top to bottom; threshold and selection
  rules as small private functions tested with literal numbers.
- The runner calls `prefilter`, then `score`, then `select`, and needs no
  knowledge of fallback or thresholds.

**Non-Goals:**

- Score calibration across scorers. Each run uses one scorer, so scales
  never need to be compared.
- Exact tokenization.

## Decisions

### Contracts in `models.py`

```python
class Candidate(BaseModel):
    query_id: str
    chunk_id: str
    prefilter: float | None = None   # similarity or BM25 value; None if not ranked
    passthrough: bool = False        # small-input passthrough

class PrefilterResult(BaseModel):
    candidates: list[Candidate]
    method: Literal["embeddings", "bm25", "none"]   # method that actually ran
    warnings: list[str] = []

class Score(BaseModel):               # extends core-contracts Score
    query_id: str
    chunk_id: str
    value: float
    scorer: str                       # "jev", "rerank", "bm25", "passthrough", ...
    display: float | None = None      # 0..1; None for passthrough
    kept: bool = False

class QueryScores(BaseModel):         # one per query; feeds `passages.scored`
    query_id: str
    scorer: str
    scored: int
    kept: int
    threshold_display: float | None
    passages: list[Score]             # kept pairs, best first

class ScoreResult(BaseModel):
    scores: list[Score]               # every pair, kept or not -> scores.jsonl
    scorer: str                       # chain entry that ran
    failed: list[Skipped] = []        # item = scorer name, reason = error text
    queries: list[QueryScores]

class Passage(BaseModel):
    n: int
    chunk_id: str
    source_id: str
    query_id: str                     # best query ID
    text: str
    heading_path: list[str]
    page_id: str | None = None
    block_ids: list[str] = []
    scorer: str
    display: float | None = None

class Context(BaseModel):
    query: str
    passages: list[Passage]           # ordered by n
    sources: list[Source]             # each source of a passage, once, first-use order
    budget_tokens: int
    used_tokens: int
```

### Settings in `config.py`

```python
class PrefilterConfig(Provider):  # provider: "embeddings" | "bm25" | "none" (default "bm25")
    top_k: int = 50
class ScoreConfig(Provider):      # existing; min_score becomes float = 1.5
    # fallback is already list[Literal["bm25", "passthrough"]] (provider-adapters)
class SelectConfig(BaseModel):
    passthrough_chars: int = 8000
    max_chunks_per_source: int = 5
    max_context_tokens: int = 16000
    file_share: float = 0.5       # 0..1
    prompt_reserve_tokens: int = 2000
class LLMConfig(Provider):        # create if `llm` is still a plain Provider
    context_window: int = 32768
    chars_per_token: float = 3.5
    token_margin: float = 1.1
```

`chars_per_token` lives on the `llm` block because it belongs to the
writing model's tokenizer: a profile that switches models sets both.

### Stage signatures

```python
# stages/prefilter.py
def pairs(queries: Sequence[Query], pages: Sequence[Page], chunks: Sequence[Chunk]) -> dict[str, list[Chunk]]
async def prefilter(queries, pages, chunks, *, method: str, embedder: Embedder | None,
                    top_k: int, passthrough_chars: int,
                    cache: MutableMapping[str, list[float]] | None = None) -> PrefilterResult

# stages/score.py
async def score(candidates: Sequence[Candidate], queries, pages, chunks, scorer: Scorer | None, *,
                cfg: ScoreConfig, on_item: Callable[[QueryScores], None] = noop) -> ScoreResult

# stages/select.py
def output_tokens(words: int) -> int                    # max(1024, 2 * words)
def budget(*, context_window: int, max_context_tokens: int, prompt_reserve_tokens: int, words: int) -> int
def estimate_tokens(text: str, *, chars_per_token: float, margin: float) -> int
def select(query: str, scores: Sequence[Score], pages, chunks, queries, *, budget_tokens: int,
           max_per_source: int, file_share: float, chars_per_token: float, margin: float) -> Context
```

`output_tokens` is also the `max_tokens` the write stage (report-writing)
passes to the LLM, so the budget and the write call agree.

### Prefilter

`pairs` maps each query ID to its chunks: web chunks whose page lists the
query ID, then all file chunks, in page order then position. A query whose
paired pages (distinct `source_id`s) total fewer than `passthrough_chars`
characters of page text gets `Candidate(passthrough=True)` for every pair.

Other queries, by method:

- `none`: every pair.
- `bm25`: `lexical.rank(query.text, texts, relative_threshold=0.0,
  max_results=top_k)`; `prefilter` value from `lexical.bm25_scores`.
- `embeddings`: collect every distinct text (query texts and chunk texts)
  whose SHA-256 is not in `cache`, call `embedder.embed` once (the adapter
  batches by `batch_size`), store the vectors in `cache`, then rank pairs
  by cosine similarity (plain Python; vectors are a few hundred floats and
  pairs a few thousand). Any exception from the embedder switches the
  whole stage to `bm25` and adds a warning.

The cache is a plain mapping supplied by the runner, which keys its
storage by model name and dimension (run-orchestration). A local dict is
used when none is given.

Alternative: numpy for cosine. Rejected: no new dependency for a few
thousand dot products.

### Score: fallback chain inside the stage

```
chain = [cfg.provider, *[f for f in cfg.fallback if f != cfg.provider]]
for name in chain:
    try:   raw = await run_scorer(name, ...)   # all non-passthrough candidates
    except Exception as exc: failed.append(Skipped(item=name, reason=str(exc))); continue
    break
```

- `passthrough`: never raises; values are `len - i` in the passthrough
  order (page `rank`, then page order, then chunk position), so "best
  first" means that order.
- `bm25`: uses `lexical` directly (the provider-adapters `bm25` adapter is
  equivalent but not required here, so fallback works even if building a
  configured adapter failed).
- any other name: the `scorer` port, which must be present with
  `scorer.name == name`; otherwise it counts as a failure with reason
  "scorer <name> not configured".

Queries run concurrently with `asyncio.gather` (the adapter's
`concurrency` and `batch_size` bound the load). The first exception
cancels the step.

The chain lives in the stage, not in the runner: "one run, one scale" is a
scoring rule, and keeping it here lets the stage be tested alone with a
failing fake. The runner only reads `ScoreResult.scorer` and `failed`.

Small-input passthrough candidates always get passthrough scores, whatever
scorer runs; they belong to queries with so little text that scoring adds
nothing.

### Thresholds, best pair, cap (one private function each)

1. `_keep_calibrated(values, min_score)`; `_keep_relative(values, r)` (best
   not positive → only the best); BM25 keeps exactly the positions returned
   by `lexical.rank(query, texts, relative_threshold=r, max_results=25)`
   over candidates in page order.
2. `_display(name, value, best)`: `jev` → `value / 3`; `bm25` →
   `value / best` (0 when `best <= 0`); others → `value`; all clamped to
   [0, 1]. Threshold display: `jev` → `min_score / 3`; `bm25` → `r`;
   others → `r * display(best)`; passthrough → None.
3. Best pair per chunk across queries by `display` (passthrough: plan
   order), ties by plan order; others `kept=False`.
4. `top_k` per query by value, ties by page order and position. Not applied
   to passthrough pairs (the token budget bounds them).

This applies the best-pair rule to every chunk, not only file chunks: a web
chunk found by two queries would otherwise be selected twice.

### Select

1. Kept scores only; join with chunks and pages.
2. Each pair's rank within its own query (0 = best by value). Per source,
   keep the `max_per_source` pairs with the lowest rank (ties by display,
   then plan order). Ranks are scale-free, so the cap does not compare
   values across queries.
3. Split into a file pool and a web pool. Each pool: one queue per query,
   best value first. `_round_robin(queues, budget) -> (taken, left)` takes
   one passage per query per round in plan order; a passage that does not
   fit goes to `left` and the round continues.
4. Phase 1: files with `floor(file_share * budget)`, web with the rest.
   Phase 2: merge both pools' `left` into per-query queues (best value
   first) and run `_round_robin` with `budget - used`.
5. Number passages `1..N` in the order taken; list sources in first-use
   order.

`estimate_tokens` is `ceil(round(len(text) / chars_per_token * margin, 6))`
(rounding first avoids float noise such as `220.00000000000003`), and a
passage costs that plus 16 for its label.

`budget()` raises `ValueError("llm.context_window ... too small")` when the
result is not positive.

Alternative: one global ranking by value. Rejected: it lets one strong
query take the whole budget, which is what round-robin prevents, and values
are not comparable across queries for uncalibrated scorers.

## Risks / Trade-offs

- [One failed rerank batch reruns the whole stage with BM25] → Simpler and
  predictable; the HTTP client already retries transient errors, so a
  failure here usually means the endpoint is down.
- [Character-ratio estimate can undercount for some tokenizers] →
  `token_margin` and `prompt_reserve_tokens` leave headroom; both are
  profile settings.
- [Clamping rerank scores hides raw logits in the UI] → `scores.jsonl`
  keeps the raw `value`; only `display` is clamped.
- [Prefilter BM25 with `relative_threshold=0.0` still drops zero-score
  chunks] → Intended: a chunk with no query term cannot help that query;
  lexical's no-match fallback keeps the opening chunks.

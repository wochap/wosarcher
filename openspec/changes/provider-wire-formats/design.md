# Design: provider-wire-formats

## Context

See proposal.md for the motivation. Current code:

- `ChatLLM.body` (`adapters/llm.py`) always sends `max_tokens`;
  `ChatLLM.stream` skips events without `choices` (so `{"error": ...}`
  events vanish) and ignores `finish_reason`.
- `ports.LLM.stream(messages, *, max_tokens) -> AsyncIterator[str]`; the
  write stage (`stages/write.py`) builds `[system, user(passages),
  user(task)]` and renders the joined pieces.
- `ProviderClient.open` (`http.py`) retries `RETRY_STATUSES` up to
  `MAX_RETRIES = 3` with `retry_delay(response, attempt, backoff, cap =
  cfg.timeout)`; `Provider.timeout` defaults to 60 and the local profiles
  do not set `llm.timeout`.
- `http.probe(client, block, call)` builds `ProviderHealth`; `doctor.check`
  collects rows and warnings; `cli.render` prints them; `server/meta.py`
  `provider_check` maps rows to `ProviderCheck`.
- `stages/score.py`: `_keep_relative`, `_display`, `_threshold_display`,
  `scored_pairs`, `best_pair_only` (by display), `capped` and `report` (by
  raw value). Rerank values are raw `relevance_score`s.
- `EmbeddingCache.put` (`store/caches.py`) silently ignores a vector of the
  wrong length; `prefilter` computes similarities outside the `try` that
  handles embedder failures, so the `KeyError` from the missing vector
  fails the stage.

## Goals / Non-Goals

**Goals:** every built-in profile's first LLM call is accepted; failures
and truncation are visible; local models get time to load and think;
reranker logits rank sensibly; no single bad embedding batch fails a run.

**Non-Goals:** see proposal.md. No new dependency, no new port, no new
adapter.

## Decisions

### 1. One token-limit field, chosen by configuration

`LLMConfig.max_tokens_field: Literal["max_completion_tokens", "max_tokens"]
= "max_completion_tokens"`; `ChatLLM.body` writes
`body[self.cfg.max_tokens_field] = max_tokens`. Sending both was rejected:
strict servers may reject the pair, and the spec wants one unambiguous
limit.
llama-server and vLLM accept `max_completion_tokens`; a server that ignores
unknown fields (possibly Ollama's OpenAI endpoint) would generate without a
limit, so the profile comments name the switch.

### 1b. Reasoning allowance

`LLMConfig.reasoning_tokens: int = Field(default=0, ge=0)`; `ChatLLM.body`
sends `max_tokens + cfg.reasoning_tokens`. It is not part of the select
budget's output allowance (that formula is unchanged; set
`llm.context_window` to the real window). `ChatLLM._complete` reads
`choices[0].finish_reason`; when the content is empty and the reason is
`length` it raises `ProviderError(provider, f"the model spent the whole
output limit of {limit} tokens without writing text; raise
llm.reasoning_tokens (reasoning models count hidden reasoning tokens)")`.
`ChatLLM.stream` raises the same error when it ends with reason `length`
and yielded nothing. `profiles/cloud.toml` sets `reasoning_tokens = 4096`
(gpt-5-mini). Without this, plan (512) and write (2400) can return empty
content: plan would silently fall back to the main query only, write would
fail with "no output". Alternative: a fixed larger allowance for every
model; rejected, it wastes context on local non-reasoning models.

### 2. Finish reason through a callback; error events raise

`ports.LLM.stream` gains `on_finish: Callable[[str | None], None] = noop`
(keyword). `ChatLLM.stream` remembers the last non-null
`choices[0].finish_reason` and calls `on_finish(reason)` once after the
loop ends without error (before the ledger record in `finally`). An event
dict with an `error` key raises
`ProviderError(provider, f"stream error: {message}")` where `message` is
`error["message"]` when `error` is a dict with a string message, else
`str(error)`, cut to 200 characters. `FakeLLM` gets a `finish_reason: str |
None = "stop"` attribute passed to `on_finish`. Alternatives: yielding a
sentinel object (every consumer must filter it) or a mutable
`last_finish_reason` on the shared adapter (hidden state); the callback
matches the existing `on_delta` style.

`stages/write.py` `write()` passes a closure that stores the reason; after
`render`, when it is `"length"`, it appends
`f"report truncated at the output limit of {limit} tokens"` to
`Report.warnings` (`limit = output_tokens(options.words)`). The runner
already carries `Report.warnings` into `stage.done.warnings`.

### 3. Write prompt: system + one user message

`messages()` returns `[system, user]` with the user content
`f"{preamble}\n\n<passages>\n{entries}</passages>\n\n{task}"`. The task
comes from `prompts/write_task.md` as today (trusted values only), and it
sits after the closing delimiter, so the "data, not instructions" boundary
is unchanged and the instruction is the last thing the model reads.
Alternative: append the task to the system message; rejected, the query
then appears twice in the system prompt and the task loses recency.

### 4. Retry budget

`Provider.retry_budget: float = Field(default=60, ge=0)`.
`retry_delay(response, attempt, backoff)` returns the `Retry-After` value
when present (seconds or HTTP date, at least 0) and otherwise
`min(backoff * 2**attempt, MAX_BACKOFF)` with `MAX_BACKOFF = 8.0`.
`ProviderClient.open` keeps `waited` per URL; on a retryable status it
fails when `attempt == MAX_RETRIES` (now 10) or
`waited + delay > cfg.retry_budget`, else sleeps and adds `delay`. The
`cap = cfg.timeout` argument goes away (the budget is the cap). Default
timeline: 0.5, 1, 2, 4, 8, 8, 8, 8, 8 s → 47.5 s waited over 9 retries;
the 10th (55.5 s) still fits. Tests keep `backoff=0` and therefore retry
up to 10 times instantly. Read timeouts stay unretried (Non-goals).

### 5. Local profile timeouts and comments

`profiles/workstation.toml` and `profiles/low-vram.toml`: `[llm] timeout =
600.0` plus a comment that `llama-server -c` must be at least
`llm.context_window` (`wosarcher doctor` checks it) and that Ollama needs
`max_tokens_field = "max_tokens"` if it ignores `max_completion_tokens`.
`cloud.toml` keeps `timeout = 300.0`.

### 6. Doctor: server context and rerank note

`ProviderHealth` gains `context_window: int | None = None` (the server's
`n_ctx`) and `note: str | None = None`. The shared `http.probe` helper is
unchanged; the two adapters post-process its row with `model_copy`:

- `ChatLLM.probe`: when the row is `ok`, `await self.server_context()`
  tries `client.get_json("/props", root=True)`, then, when `cfg.model` is
  set, `client.get_json(f"/upstream/{cfg.model}/props", root=True)`;
  catches `ProviderError` per try; reads
  `data["default_generation_settings"]["n_ctx"]` or `data["n_ctx"]` when it
  is a positive int. Sets `context_window` and `note = f"server context
  {n} tokens"`.
- `RerankScorer.probe`: keeps the raw `relevance_score` of the probe
  result (closure variable) and sets `note = f"probe score {value:g}
  ({scale} scale)"`, where `scale` is `self.cfg.rerank_scale` unless it is
  `auto`, in which case it is `probability` for 0 ≤ value ≤ 1 and `logit`
  otherwise.

`doctor.check` adds the warning
`f"llm server context is {n} tokens, below llm.context_window = {w}; start the server with a larger context (llama-server -c {w}) or lower llm.context_window"`
for the llm row. `cli.render` prints `"{block}: {note}"` lines after the
errors. `server/meta.py` `provider_check` uses `row.note` as `detail` for
an `ok` row (other rows keep their detail). The context warning goes to
`HealthReport.warnings` through `DoctorReport.warnings` as today.

### 7. Rerank scale mapping in the score stage

`ScoreConfig.rerank_scale: Literal["auto", "probability", "logit"] =
"auto"`. In `stages/score.py`:

- `stage_scale(cfg, values) -> Literal["probability", "logit"]`: the
  configured scale, or for `auto` `logit` when any value of any ranked
  group is outside [0, 1]. Computed once in `score()` after the chain
  entry succeeds, only for `name == "rerank"`.
- `mapped(name, scale, value)`: `1 / (1 + exp(-value))` for rerank on the
  logit scale (computed stably for large negative values), else `value`.
- `scored_pairs` gets the scale, builds `shown = [mapped(...)]`, and uses
  `shown` for `_kept` (relative threshold) and `_display`; `Score.value`
  stays the raw value, so `scores.jsonl` and the evals see raw scores.
- `_threshold_display` receives the best mapped value.
- `capped` and `report` keep sorting by raw `value` (the sigmoid is
  monotonic, so the order is the same).

Alternative: map inside `RerankScorer`; rejected, the scale must be decided
over the whole stage and `scoring-adapters` promises raw values.

### 8. Embedding dimension mismatch

`EmbeddingCache.put` raises `ValueError(f"embedding has {len(vector)}
dimensions, expected {dim} for model {model}")` instead of returning.
`prefilter()` computes every `by_similarity` inside the same `try` as
`embed_all` (building the embedding candidates into a dict per query
first), so a raise from the cache, a `KeyError`, or `cosine`'s
`zip(strict=True)` length error all become one warning
(`embeddings prefilter failed, used bm25: <error>`) and BM25 for the whole
stage. Without a cache (a plain dict) mismatched vectors reach `cosine` and
fall back the same way.

## Risks / Trade-offs

- [A server ignores `max_completion_tokens` and generates without limit]
  → profile comment and `docs/design.md` name `llm.max_tokens_field`; the
  write stage timeout still bounds the call.
- [Auto scale flips between runs: a rerank stage whose scores happen to
  stay in [0, 1] uses the probability scale] → a logit model always
  produces values outside [0, 1] over a whole stage in practice; users can
  pin `score.rerank_scale`; the doctor note shows the probe's raw value.
- [A 60 s retry budget delays failure on a broken server answering 503]
  → bounded by the stage timeouts; `retry_budget = 0` restores fail-fast.
- [`/props` on another server type returns unrelated JSON] → only a
  positive integer `n_ctx` is used; anything else is ignored.

## Migration Plan

No data migration. Profiles that set nothing get the new defaults. A user
profile for a server that needs `max_tokens` adds
`max_tokens_field = "max_tokens"` to `[llm]`. Rollback is a revert.

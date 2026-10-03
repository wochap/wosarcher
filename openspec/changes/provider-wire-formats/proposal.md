# Proposal: provider-wire-formats

## Why

The Fable review found that the shipped providers break or silently degrade
on the first real run: OpenAI reasoning models (the `cloud` profile's
`gpt-5-mini`) reject `max_tokens` with HTTP 400; a report cut by the output
limit, or a llama-server error sent mid-stream, ends quietly with no
warning; local models time out after 60 s of prompt processing and give up
after ~3.5 s of 503s while loading; a context window smaller than
`llm.context_window` is never detected; raw reranker logits make the
relative threshold keep one passage per query; strict chat templates reject
two consecutive user messages; and an embedding of an unexpected dimension
fails the whole run instead of falling back to BM25. This change fixes the
provider wire formats before the first live research run (it builds on
`server-robustness` only for ordering; it does not depend on its code).

## What Changes

- **LLM token limit field** (Fable 1.1): requests send
  `max_completion_tokens` by default; `llm.max_tokens_field =
  "max_tokens"` switches to the old field for servers that need it.
- **Reasoning allowance**: new `llm.reasoning_tokens` (default 0; the
  `cloud` profile sets 4096) is added to every LLM request's limit; an
  answer with empty content and finish reason `length` fails with an error
  naming `llm.reasoning_tokens`.
- **Truncated reports** (Fable 1.4): the streaming call reports the final
  `finish_reason`; when it is `length`, the report gets a warning naming the
  output limit.
- **Errors inside a stream** (Fable 2.9): a stream event with an `error`
  object fails the write with a provider error carrying its message.
- **Timeouts and retries for local models** (Fable 2.2, 2.3): the
  `workstation` and `low-vram` profiles set `llm.timeout = 600`; retries on
  429/502/503/504/529 continue with capped exponential backoff while the
  total wait stays within a new per-block `retry_budget` (default 60 s, at
  most 10 retries).
- **Context window check** (Fable 1.5): the LLM probe reads the server's
  `n_ctx` from `GET <root>/props` (llama-server; also
  `<root>/upstream/<model>/props` behind llama-swap) when available, and
  `wosarcher doctor` warns when it is below `llm.context_window`. Warning
  only; the exit code is unchanged.
- **Reranker score scale** (Fable 1.2): new `score.rerank_scale`
  (`auto` default, `probability`, `logit`); logits are mapped through a
  sigmoid before the relative threshold and the display score, so
  negative or large logits keep a sensible set of passages. The doctor
  shows the rerank probe's raw score and the scale it implies.
- **Write prompt layout** (Fable 2.4): the writer sends `system` then one
  `user` message (instruction, delimited passages, then the task), so
  templates that require alternating roles work.
- **Embedding dimension mismatch** (Fable 3.2): a vector whose dimension
  differs from the cached identity is never stored; the prefilter treats
  it as an embedder failure and falls back to BM25 with a warning.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `llm-adapter`: token-limit field; reasoning allowance and empty-answer error; stream error events; finish reason.
- `report-writing`: one user message with data then task; truncation
  warning.
- `provider-http`: retry budget instead of a fixed three retries.
- `run-config`: `retry_budget` in every provider block; `llm.reasoning_tokens`;
  local profiles' LLM timeout; `cloud` reasoning allowance.
- `provider-doctor`: server context window check; rerank probe score note.
- `passage-scoring`: rerank scale mapping for thresholds and display;
  prefilter fallback on a dimension mismatch.
- `run-store`: embedding cache refuses vectors of another dimension.

## Non-goals

- Retrying read timeouts or moving to a fallback URL on them (the longer
  `llm.timeout` covers slow first tokens).
- Changing the output allowance formula (`max(1024, 2 * words)`) or the
  plan stage's 512-token limit.
- llama-server `n_ubatch` limits on long chunks (Fable 2.5), Firecrawl
  credit accounting (2.7), SearXNG redirects (2.8).
- Checking Ollama's `num_ctx` (it has no `/props`; documented in profile
  comments only).
- Frontend changes: display scores stay 0 to 1 and are computed by the
  server, so the UI is unchanged.

## Impact

- Code: `src/wosarcher/adapters/llm.py`, `adapters/rerank.py`,
  `adapters/fakes.py`; `src/wosarcher/ports.py` (`LLM.stream` gains
  `on_finish`); `src/wosarcher/stages/write.py`, `stages/score.py`,
  `stages/prefilter.py`; `src/wosarcher/store/caches.py`;
  `src/wosarcher/http.py` (`ProviderClient.open`, `retry_delay`, `probe`);
  `src/wosarcher/config.py` (`Provider.retry_budget`,
  `LLMConfig.max_tokens_field`, `ScoreConfig.rerank_scale`);
  `src/wosarcher/models.py` (`ProviderHealth.context_window`,
  `ProviderHealth.note`); `src/wosarcher/doctor.py`, `cli/__init__.py`
  (`render`), `server/meta.py` (`provider_check` detail);
  `src/wosarcher/prompts/` (passages and task in one message);
  `src/wosarcher/profiles/workstation.toml`, `low-vram.toml`, `cloud.toml`
  comments.
- The recorded-run fixture (`tests/fixtures/runs/20260101-000000-fixture/`)
  and `tests/fixtures/http/` bodies that assert the request shape are
  regenerated.
- Docs: `docs/design.md` sections "Endpoints and devices" (timeouts,
  retries), "Scoring", "Select" (`max_tokens` wording), "Prompt injection",
  "Adapters", "Configuration", "Frontend decisions" (Scores), and
  "Commands" (doctor); README "Configuration".
- No new dependency.

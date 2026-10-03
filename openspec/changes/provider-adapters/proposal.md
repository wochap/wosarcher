# Proposal

## Why

Stages (research-collection, passage-ranking, report-writing) are written
against the ports from core-contracts and need real implementations behind
them: SearXNG for search, Firecrawl for pages, an embeddings endpoint for
the prefilter, a reranker or Jev for scoring, and a chat model for planning
and writing. Users also need one command that tells them, before a long
run, whether every configured endpoint answers and whether `exclusive` GPU
mode can actually unload models.

## What Changes

- One adapter per wire format in `src/wosarcher/adapters/`, each on the
  shared `ProviderClient` and `UsageLedger`:
  - `searxng.py` (Searcher): SearXNG JSON API with `max_results`,
    `language`, `time_range`.
  - `firecrawl.py` (Fetcher): Firecrawl scrape to markdown, main content
    only, per-page timeout, `max_chars` cap, PDFs at URLs; self-hosted or
    cloud.
  - `embeddings.py` (Embedder): OpenAI-compatible `/embeddings`, batched,
    base64 payloads when the server supports them, reports the model name
    and dimension for cache keys.
  - `rerank.py` (Scorer, uncalibrated): Cohere/Jina-style `/rerank`.
  - `jev.py` (Scorer, calibrated 0 to 3): TypeSafe `/systemone` usefulness
    rubric, concurrency 64.
  - `bm25.py` (Scorer, uncalibrated): wraps `lexical.py`.
  - `passthrough.py` (Scorer): the terminal fallback, keeps input order.
  - `llm.py` (LLM): OpenAI-compatible chat, complete and streaming, with
    usage.
  - `fakes.py`: a fake for every port, for stage and runner tests.
- `release()` on every HTTP adapter: llama-swap `/unload`, Ollama
  `keep_alive: 0`, otherwise a no-op. `probe()` on every HTTP adapter for
  health checks.
- `build.py`, the composition root: `Settings` to adapters through dicts of
  constructors.
- `doctor.py` and `wosarcher doctor [--profile] [--set] [--json]`: per
  configured provider, reachable, model name, latency of one small request,
  unload support; warns when `exclusive` GPU policy meets a model that
  cannot be unloaded.
- Additions to core-contracts code this change needs (see Impact).

## Non-goals

- No pipeline stages, no prefilter logic, no fallback chain between
  scorers (passage-ranking), no runner or exclusive-mode orchestration
  (run-orchestration). This change only provides `release()`.
- No search providers other than SearXNG; no local PDF parsing.
- No Firecrawl crawl, map, or extract endpoints; scrape only.
- No client-side prompt templates for rerankers (servers apply the model's
  own rerank template).
- No `GET /providers/health` route; server-api calls `doctor` later.
- No price tables; prices stay configuration.

## Capabilities

### New Capabilities

- `search-adapter`: web search through a SearXNG instance.
- `fetch-adapter`: fetching web pages and PDFs as markdown through
  Firecrawl.
- `embedding-adapter`: text embeddings from an OpenAI-compatible endpoint,
  with a model identity for cache keys.
- `scoring-adapters`: the `rerank`, `jev`, `bm25`, and `passthrough`
  scorers and their score scales.
- `llm-adapter`: chat completion and streaming from an OpenAI-compatible
  endpoint, with usage.
- `provider-doctor`: `wosarcher doctor`, health probes, and model release.

### Modified Capabilities

None (core-contracts is not archived yet; its additions are listed below).

## Impact

- New code: `src/wosarcher/adapters/` (eight adapters plus `fakes.py`),
  `src/wosarcher/build.py`, `src/wosarcher/doctor.py`,
  `src/wosarcher/prompts/jev.toml`, `wosarcher doctor` in `cli.py`, tests
  under `tests/adapters/`.
- Additions to core-contracts code:
  - `http.py`: `ProviderClient.request` (the retry and fallback loop shared
    by `post_json`, a new `get_json`, and server-root calls), `stream_lines`
    for server-sent events, and plain functions `unload` and
    `unload_supported`.
  - `config.py`: `SearchConfig` (`max_results`, `language`, `time_range`),
    `FetchConfig` (`max_chars`, `only_main_content`, `page_timeout`),
    `concurrency` becomes optional with per-adapter defaults,
    `score.fallback` limited to `bm25` and `passthrough`,
    `run.gpu_policy` if absent.
  - `models.py`: `EmbedderInfo`, `ProviderHealth`, `DoctorReport`.
  - `ports.py`: `Embedder.describe()` and a `Managed` Protocol (`probe`,
    `release`).
- `scripts/check_architecture.py`: new top-level part `doctor` (imports
  `models`, `ports`, `config`), allowed in `server` and `cli`.
- No new dependencies (respx and pytest-asyncio come from core-contracts).
- docs/design.md sections implemented: Adapters, Endpoints and devices
  (release, failover, payload size, cache correctness, health), Scoring
  (scorer scales and calibration), Costs (usage per adapter), Commands
  (`wosarcher doctor`), Patterns used (composition root). Changed:
  Endpoints and devices (`base_url` includes the API version), Adapters
  (default paths and concurrency), Scoring (bm25 and passthrough values,
  fallbacks limited to built-in scorers), Package layout (`doctor.py`).

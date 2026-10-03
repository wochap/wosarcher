# Proposal

## Why

Every later capability (adapters, stages, run store, server, frontend, skill)
depends on the same data contracts, the same configuration, and the same way
of talking to HTTP providers. Building these first, with tests, keeps every
later change small and lets adapters and stages be written against stable
types.

## What Changes

- Python project scaffold: `pyproject.toml` with uv, package `wosarcher`,
  console script `wosarcher`, ruff, basedpyright (strict), pytest.
- Data contracts as Pydantic models: queries, search hits, sources, pages,
  chunks, scores, selected context, report, writing options, and the run
  request. Deterministic IDs for sources and chunks.
- Ports: Protocols for Searcher, Fetcher, Embedder, Scorer, and LLM.
- Configuration: built-in and user profiles, precedence (defaults < profile <
  environment < CLI or request), per-field `--set` overrides, provider blocks
  with one shared shape, secret redaction.
- Provider HTTP client: shared async client with timeouts, retry with
  backoff, per-provider concurrency limit, ordered fallback URLs, and usage
  and cost recording.
- CLI: `wosarcher profile list`, `wosarcher profile show`, `wosarcher profile use`, and
  `wosarcher schema` (JSON Schema of the contracts, for frontend type generation).

## Non-goals

- No adapters (SearXNG, Firecrawl, embeddings, rerank, Jev, LLM), no BM25,
  no pipeline stages, no run store, no events, no server. Each is a later
  change.
- No `wosarcher doctor`; it needs the adapters.
- No provider health checks or model unloading.

## Capabilities

### New Capabilities

- `run-config`: how a run's configuration is resolved: profiles, profile
  selection, precedence, overrides, validation, and secret redaction.
- `data-contracts`: the shape and identity of the data that flows between
  stages, and its published JSON Schema.
- `provider-http`: how the tool calls HTTP providers: timeouts, retries,
  concurrency limits, fallback URLs, and usage recording.

### Modified Capabilities

None.

## Impact

- New code: `wosarcher/models.py`, `wosarcher/ports.py`,
  `wosarcher/config.py`, `wosarcher/http.py`, `wosarcher/cli.py`,
  `wosarcher/profiles/*.toml`, tests.
- New dependencies: pydantic, httpx, typer, rich; dev:
  pytest, pytest-asyncio, respx, ruff, basedpyright.
- docs/design.md sections implemented: Package layout (models, ports, config,
  http), Configuration, Switching providers without a rebuild (client side),
  Endpoints and devices (provider block fields), Costs (recording only),
  Writing options (model only), Tech stack.
- docs/design.md changes: the package lives in `src/wosarcher`, the CLI
  command is `wosarcher`, and environment variables use the `WOSARCHER_`
  prefix; configuration is resolved by own code with the standard library
  `tomllib`, not pydantic-settings.

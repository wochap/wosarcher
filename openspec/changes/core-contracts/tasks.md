# Tasks

## 1. Project scaffold

- [ ] 1.1 Create `pyproject.toml` (uv, src layout, package `wosarcher`, console script `wosarcher`, Python >=3.13) with dependencies pydantic, httpx, typer, rich and dev dependencies pytest, pytest-asyncio, respx, ruff, basedpyright; verify `uv sync` succeeds in the Nix dev shell and `uv run wosarcher --help` prints the command list
- [ ] 1.2 Configure ruff (lint and format) and basedpyright (strict) in `pyproject.toml`; verify `scripts/check-backend` runs ruff and the architecture check (no longer skipped) and passes, and `uv run basedpyright` passes on the empty package
- [ ] 1.3 Add a pytest smoke test that imports `wosarcher`; verify `uv run pytest` passes

## 2. Data contracts

- [ ] 2.1 Implement URL normalisation in `models.py`; verify unit tests for lowercase scheme and host, fragment removal, trailing slash, tracking parameters removed, parameter order, and meaningful parameters kept (spec: URL normalisation)
- [ ] 2.2 Implement `source_id` and `chunk_id` helpers; verify tests that normalised URLs share an ID, identical file content shares an ID, and chunking the same input twice gives the same IDs (spec: Source identity, Chunk identity)
- [ ] 2.3 Implement the contract models (run request, query, hit, source, page, chunk, score, context, report, writing options, and `Message` and `Completion` as in design.md) as frozen models with `extra="forbid"`; verify round-trip tests for every type and a test that an unknown field is rejected (spec: Contract types)
- [ ] 2.4 Implement writing option defaults and validation; verify tests for the defaults, `words = 0` failing, and an unknown `citation_marker` failing (spec: Writing options)
- [ ] 2.5 Verify a test that one chunk scored against two queries gives two scores naming the scorer (spec: Scores are pairs)

## 3. Ports

- [ ] 3.1 Define the Searcher, Fetcher, Embedder, Scorer, and LLM Protocols in `ports.py`; verify basedpyright accepts a minimal fake for each Protocol in `tests/fakes.py` and rejects a fake with a wrong method signature (checked by a typing test file)

## 4. Configuration

- [ ] 4.1 Define the settings models (`Prices`, `Provider`, stage blocks, `Settings`) with defaults; verify a test that defaults validate and that an invalid `release` value fails naming the allowed values (spec: Provider block shape)
- [ ] 4.2 Add built-in profiles `low-vram.toml`, `workstation.toml`, and `cloud.toml` as package data; verify a test that each validates
- [ ] 4.3 Implement profile discovery (user directory over built-in) and profile selection order; verify tests for built-in, user override, unknown profile listing available names, option over environment, and the stored default (spec: Profiles, Profile selection)
- [ ] 4.4 Implement environment parsing (`WOSARCHER_` prefix, `__` nesting) and `--set` parsing with TOML values; verify tests for typed overrides and an unknown key error (spec: Field overrides)
- [ ] 4.5 Implement `resolve()` with deep merge and source tracking; verify tests for every precedence scenario and that an invalid profile value error names the file and field (spec: Precedence, Validation)
- [ ] 4.6 Implement secret redaction for display and artifacts; verify tests that `api_key` shows `***` when set from a profile or from `WOSARCHER_SCORE__API_KEY` (spec: Secret redaction)

## 5. Provider HTTP client

- [ ] 5.1 Implement `ProviderClient.post_json` with timeouts and the Bearer header; verify respx tests that the header is sent and that error messages never contain the key (spec: Timeouts, Authentication header)
- [ ] 5.2 Implement retries on 429, 502, 503, 504, 529 with backoff and capped `Retry-After`; verify respx tests for 429 then 200, 400 not retried, and 503 failing after 4 attempts (spec: Retries)
- [ ] 5.3 Implement fallback URLs on connection failure only; verify tests for primary down, primary answering 400, and all endpoints down listing every URL (spec: Fallback URLs)
- [ ] 5.4 Implement the per-provider concurrency semaphore; verify a test with `concurrency = 2` and 5 calls that tracks the maximum in flight (spec: Concurrency limit)
- [ ] 5.5 Verify a test that cancelling an in-flight call releases its slot and lets a waiting call start (spec: Cancellation)
- [ ] 5.6 Implement `UsageLedger`; verify tests that usage is summed per provider and stage and that cost is 0 without prices (spec: Usage recording)

## 6. CLI

- [ ] 6.1 Implement `wosarcher profile list`, `wosarcher profile show`, and `wosarcher profile use` with `--profile` and `--set` options; verify CLI tests with a temporary `XDG_CONFIG_HOME` for listing with the active marker, redacted output, and persistence of `use` (spec: Profile commands)
- [ ] 6.2 Implement `wosarcher schema`; verify a test that two runs print byte-identical output that covers every contract type (spec: Published JSON Schema)

## 7. Documentation

- [ ] 7.1 Update docs/design.md: package under `src/wosarcher`, CLI command `wosarcher`, `WOSARCHER_` environment prefix, configuration resolved by own code with `tomllib` instead of pydantic-settings; verify the Package layout, Tech stack, and Configuration sections match the code
- [ ] 7.2 Verify `scripts/check --full` passes and `openspec validate core-contracts --strict` passes

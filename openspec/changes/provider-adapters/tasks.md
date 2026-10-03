# Tasks

## 1. Contract and HTTP additions

- [ ] 1.1 In `config.py`, add `SearchConfig` and `FetchConfig` (fields and defaults in design.md), make `Provider.concurrency` `int | None = None`, type `ScoreConfig.fallback` as `list[Literal["bm25", "passthrough"]]`, ensure `RunConfig.gpu_policy: Literal["shared", "exclusive"] = "shared"` exists, and add the validators (`release = "ollama"` needs `model`; `fetch.page_timeout < fetch.timeout`); verify `tests/test_config.py` tests `test_time_range_invalid`, `test_page_timeout_must_be_below_timeout`, `test_fallback_rejects_remote_scorer`, and `test_ollama_release_needs_model` pass and the built-in profiles still validate (specs: search-adapter Search settings, fetch-adapter Page timeout below request timeout, scoring-adapters Built-in fallbacks only, provider-doctor Model release)
- [ ] 1.2 In `models.py`, add `EmbedderInfo`, `ProviderHealth`, and `DoctorReport` as frozen models with `extra="forbid"`; verify a round-trip test for each and that `wosarcher schema` output includes them
- [ ] 1.3 In `ports.py`, add `Embedder.describe() -> EmbedderInfo` and the `Managed` Protocol (`probe`, `release`); update the core-contracts typing test fakes so basedpyright still passes
- [ ] 1.4 In `http.py`, extract the retry/fallback/semaphore loop of `post_json` into `ProviderClient.request(method, path, *, json, params, root)`, rebuild `post_json` on it, add `get_json`, add `status` to `ProviderError`, and implement `root=True` (strip a trailing `/` then `/v1` from each URL); verify the existing provider-http tests still pass plus `test_get_json_params` and `test_root_path_strips_v1` (respx)
- [ ] 1.5 In `http.py`, add `ProviderClient.stream_lines(path, body)` (same loop until 2xx, then yields SSE `data:` payloads while holding the semaphore slot); verify respx tests `test_stream_lines_yields_data`, `test_stream_retries_before_first_line` (503 then 200), and `test_stream_close_releases_slot` (concurrency 1, close the generator after one line, a second call proceeds)
- [ ] 1.6 In `http.py`, add `unload(client, release, model)` and `unload_supported(client, release)`; verify respx tests for llama-swap `GET /unload` at the server root, Ollama `POST /api/generate` with `keep_alive: 0`, no request for `none`, and `unload_supported` true on 200 and false on 404 and on connection error (spec: provider-doctor Model release, Unload support check)

## 2. Search and fetch adapters

- [ ] 2.1 Create `adapters/searxng.py` with `SearxngSearcher.search` (params, skip URL-less results, dedupe by normalised URL, cap, rank, usage record, 403 hint); verify `tests/adapters/test_searxng.py` tests `test_results_become_hits`, `test_duplicate_urls`, `test_no_results`, `test_result_cap`, `test_language_and_time_range_sent`, `test_defaults_omit_parameters`, `test_forbidden_hint`, and `test_request_counted` pass (spec: search-adapter)
- [ ] 2.2 Add `probe()` and a no-op `release()` to `SearxngSearcher`; verify `test_probe_ok` (status ok, latency set, unload `n/a`) and `test_probe_failed` (connection refused → status failed with the URL in `error`)
- [ ] 2.3 Create `adapters/firecrawl.py` with `FirecrawlFetcher.fetch` (body, title fallback, `max_chars` cut, failure checks, credits); verify `tests/adapters/test_firecrawl.py` tests `test_page_fetched`, `test_no_auth_header_without_key`, `test_pdf_markdown`, `test_long_page_cut`, `test_target_not_found`, `test_success_false`, `test_empty_page`, and `test_credits_recorded` pass (spec: fetch-adapter)
- [ ] 2.4 Add `probe()` (scrape `https://example.com`) and a no-op `release()` to `FirecrawlFetcher`; verify `test_probe_ok` and that `release()` sends no request

## 3. Embedding adapter

- [ ] 3.1 Create `adapters/embeddings.py` with `OpenAIEmbedder.embed` (batches, `asyncio.gather`, index ordering, count and dimension checks, usage); verify `tests/adapters/test_embeddings.py` tests `test_order_restored`, `test_missing_vector`, `test_two_batches`, and `test_tokens_recorded` pass (spec: embedding-adapter OpenAI-compatible embeddings, Batching, Embedding usage)
- [ ] 3.2 Add base64 request and decoding, float passthrough, and the one-time switch to floats after a 400/422; verify `test_base64_decoded` (encode `[0.5, -1.0]` with `struct.pack("<2f", ...)`), `test_server_ignores_base64`, and `test_server_rejects_base64` pass (spec: Base64 payloads)
- [ ] 3.3 Add `describe()` with the cached `EmbedderInfo` and an `asyncio.Lock`; verify `test_reported_model_wins` and `test_identity_learned_once` (two concurrent `describe()` calls, one request) pass (spec: Model identity)
- [ ] 3.4 Add `probe()` (embed one text; model and dimension from `describe`) and `release()` (calls `http.unload`); verify `test_probe_reports_model` and `test_release_llama_swap` pass

## 4. Scoring adapters

- [ ] 4.1 Create `adapters/rerank.py` with `RerankScorer` (batches, `results` or `data`, index mapping, coverage check, usage, empty input sends nothing); verify `tests/adapters/test_rerank.py` tests `test_index_mapping_across_batches`, `test_data_key_accepted`, `test_missing_document`, `test_empty_chunks_no_request`, `test_usage_tokens_and_units`, and `test_not_calibrated` pass (spec: scoring-adapters Scorer results, Rerank scorer)
- [ ] 4.2 Add `probe()` (one query, one document) and `release()` to `RerankScorer`; verify `test_probe_ok` and `test_release_ollama_posts_keep_alive` pass
- [ ] 4.3 Create `src/wosarcher/prompts/jev.toml` with `instructions` and `criteria` from design.md, included as package data; verify a test that loads it with `importlib.resources` and finds four criteria
- [ ] 4.4 Create `adapters/jev.py` with `JevScorer` (one request per chunk, `state` untouched, `safe_substitute(query=...)`, default model `jev-latest`, range check, usage); verify `tests/adapters/test_jev.py` tests `test_calibrated_score`, `test_scraped_text_not_templated`, `test_bad_answer`, `test_out_of_range_score`, and `test_input_tokens_recorded` pass (spec: Jev scorer)
- [ ] 4.5 Add `probe()` and a `release()` that only unloads when `release != "none"` to `JevScorer`; verify `test_probe_ok`
- [ ] 4.6 Create `adapters/bm25.py` with `Bm25Scorer` over `lexical.bm25_scores` (relative values, first-25 fallback); verify `tests/adapters/test_bm25.py` tests `test_relative_values` and `test_no_keyword_overlap` (30 chunks) pass (spec: BM25 scorer)
- [ ] 4.7 Create `adapters/passthrough.py` with `PassthroughScorer`; verify `test_order_kept` (spec: Passthrough scorer)

## 5. LLM adapter

- [ ] 5.1 Create `adapters/llm.py` with `ChatLLM.complete` (body, first choice content, null → empty, usage under the adapter's stage); verify `tests/adapters/test_llm.py` tests `test_completion_returned` and `test_null_content` pass (spec: llm-adapter Chat completion)
- [ ] 5.2 Add `ChatLLM.stream` on `ProviderClient.stream_lines` (`stream_options.include_usage`, `[DONE]`, skip empty deltas and choice-less events, usage recorded in `finally`); verify `test_deltas_in_order`, `test_error_mid_stream` (respx stream that raises after one event; one request only), and `test_consumer_stops_early` pass (spec: Streaming)
- [ ] 5.3 Add `probe()` (one-token completion, reported `model`) and `release()`; verify `test_probe_reports_model` (`qwen3-8b-q4_k_m`) and `test_release_none_sends_nothing` pass

## 6. Fakes and composition root

- [ ] 6.1 Create `adapters/fakes.py` with `FakeSearcher`, `FakeFetcher`, `FakeEmbedder`, `FakeScorer`, and `FakeLLM` as described in design.md, each with `probe()` and `release()`; verify `tests/adapters/test_fakes.py` checks each fake against its Protocol with a typed assignment (basedpyright) and one behaviour test per fake; delete `tests/fakes.py` from core-contracts and point its typing test at `adapters/fakes.py`
- [ ] 6.2 Add the `Adapters` dataclass to `ports.py` and `DEFAULT_CONCURRENCY` to `config.py`; create `build.py` with the `SCORERS` and prefilter constructor dicts, and `build(settings, http, ledger)`; verify `tests/test_build.py` tests `test_build_workstation_profile` (types of each field), `test_unknown_provider_names_allowed_values`, `test_bm25_prefilter_has_no_embedder`, `test_none_prefilter_has_no_embedder`, `test_scorers_in_fallback_order` (`jev`, `bm25`, `passthrough`), `test_jev_default_concurrency_64` (spec: Jev scorer Default concurrency), and `test_planner_writer_share_client` (spec: llm-adapter Shared limit, respx with a slow first response)
- [ ] 6.3 Verify `test_planner_and_writer_usage_separate` in `tests/test_build.py`: one `complete` on the planner and one on the writer record under `plan` and `write` (spec: llm-adapter LLM usage per stage)

## 7. Doctor

- [ ] 7.1 Add `"doctor": {"models", "ports", "config"}` to `ALLOWED` in `scripts/check_architecture.py` and add `"doctor"` to the `server` and `cli` sets (justification: the health check is shared by the CLI and, later, `GET /providers/health`); verify `scripts/check` reports `architecture: ok`
- [ ] 7.2 Create `doctor.py` with `exclusive_warnings(settings)`; verify `tests/test_doctor.py` tests `test_shared_device_without_release`, `test_separate_devices_no_warning`, and `test_shared_policy_no_warning` pass (spec: Exclusive GPU warnings)
- [ ] 7.3 Add `check(settings, managed) -> DoctorReport` (concurrent probes, built-in rows, unload warnings); verify `test_all_healthy`, `test_one_endpoint_down` (other rows still present), `test_builtin_scorer_row`, and `test_release_unsupported_warns` pass using fakes (spec: Doctor command, Unload support check)
- [ ] 7.4 Add `wosarcher doctor [--profile] [--set] [--json]` to `cli.py` (resolve → `build` with one `httpx.AsyncClient` → `doctor.check`; rich table; exit 1 on any failed row; help text says the Firecrawl probe spends one credit on the cloud API); verify `tests/test_cli_doctor.py` tests `test_doctor_all_ok_exit_0`, `test_doctor_failure_exit_1`, `test_doctor_other_profile`, and `test_doctor_json` with respx and a temporary `XDG_CONFIG_HOME` (spec: Doctor command, Probes)

## 8. Documentation and gate

- [ ] 8.1 Update docs/design.md: Endpoints and devices (`base_url` includes the API version, rerank example `http://desktop.lan:8001/v1`, server root for unload and health, llama-swap `/unload` and `/running`, Ollama `/api/generate` with `keep_alive: 0`); Adapters (path table and default concurrency per adapter); Scoring (bm25 values relative to the best chunk, passthrough value 1.0, `score.fallback` only `bm25` and `passthrough`); Package layout (`doctor.py`, `prompts/jev.toml`); Commands (`wosarcher doctor` flags and exit code); verify each section matches the code
- [ ] 8.2 Verify with `wc -l src/wosarcher/adapters/*.py` that every adapter file is under 200 lines
- [ ] 8.3 Verify `scripts/check --full` passes and `openspec validate provider-adapters --strict` passes

# Tasks

## 1. Setup

- [ ] 1.1 Add `pythonpath = ["."]` to `[tool.pytest.ini_options]` and `evals` to basedpyright `include` in `pyproject.toml`; create `evals/__init__.py`; verify `uv run pytest -q` still passes and `uv run basedpyright` checks `evals/`

## 2. Recorded responses and fixture

- [ ] 2.1 Add recorded response bodies under `tests/fixtures/http/` (two SearXNG queries plus the main query, four Firecrawl pages, `plan.json`, `write.sse` citing `[1]` and `[2]`) and `tests/fixtures/http/notes.md`, total under 40 KB; verify each JSON file parses with `json.loads`
- [ ] 2.2 Add `tests/fixtures/profiles/e2e.toml` (search `http://searxng.test`, fetch `http://firecrawl.test`, llm `http://llm.test/v1`, prefilter and score `bm25`); verify a test that it resolves with `config.resolve` when `XDG_CONFIG_HOME` points at `tests/fixtures/`
- [ ] 2.3 Implement `tests/fixtures/recorded.py` with `recorded_router()` as in design.md; verify tests that a known query returns its body, an unknown URL on Firecrawl returns 404, and a request to another host raises `AllMockedAssertionError` naming the URL (spec: Unexpected request)

## 3. End-to-end test

- [ ] 3.1 Write `tests/test_e2e_run.py::test_full_run`: run `wosarcher run "q" --profile e2e --attach tests/fixtures/http/notes.md` with `recorded_router()`; assert exit 0, `run.done` last, every artifact from the run-store table exists, `seq` is 1..n, and every `[n]` in `report.md` is a passage number in `context.json` (spec: End-to-end run without live services)
- [ ] 3.2 Write `tests/test_e2e_run.py::test_until_select_json`: `--until select --json` prints a document that validates as `RunOutput` with `report` null and a non-empty `context`

## 4. Committed recorded run

- [ ] 4.1 Implement `tests/fixtures/make_recorded_run.py` (in-process CLI, `recorded_router()`, `--run-id 20260101-000000-fixture`, output under `tests/fixtures/runs/`); run it and commit `tests/fixtures/runs/20260101-000000-fixture/`; verify the directory has every artifact and is under 200 KB
- [ ] 4.2 Write `tests/test_fixture_run.py::test_fixture_parses`: parse every artifact with its model and every `events.jsonl` line with `parse_event`, failing with the artifact name (spec: Recorded-run fixture)
- [ ] 4.3 Write `tests/test_fixture_run.py::test_fixture_forks`: copy the fixture to `tmp_path`, run `wosarcher fork <id> --from score --set score.provider=bm25 --until select --json` with respx active and no routes; assert status `done` (spec: Fixture forks)

## 5. Replay

- [ ] 5.1 Add `evals/variants.toml` (bm25, bm25-wide, rerank, jev, prefilter-embeddings, prefilter-bm25) and `load_variants(path) -> dict[str, Variant]` in `evals/replay.py`; verify tests that the shipped file loads and that `from = "fetch"` fails naming the variant (spec: Variants)
- [ ] 5.2 Implement `fork(run_id, variant, write, env) -> ForkResult` (subprocess `python -m wosarcher fork ... --json`); verify a test on the copied fixture that the `bm25` variant returns status `done` and a new run ID, and a test that a variant with `score.topk=1` returns status `failed` with the error text (spec: Replay, Failed fork)
- [ ] 5.3 Implement `main()` for `python -m evals.replay --runs ID... | --all --variants NAME... --out DIR [--write] [--force]` writing `results.jsonl` and skipping finished pairs; verify a test with two copies of the fixture run (second via `wosarcher fork <id> --from prefilter --until select`, which needs no network) and variants `bm25` and `bm25-wide` that writes four records, and that a second call writes none (spec: Two variants)
- [ ] 5.4 Verify a test that in a fork from `score` the `stage.done` events for search, fetch, and chunk carry `copied_from` and its `hits.jsonl` and `chunks.jsonl` equal the parent's byte for byte (spec: Search and fetch held constant)

## 6. Metrics

- [ ] 6.1 Implement `selected_chunk_ids`, `context_size`, `stage_seconds`, and `jaccard` in `evals/metrics.py`; verify unit tests on hand-written run directories: Jaccard {1,2,3} vs {2,3,4} = 0.5, both empty = 1.0, stage seconds exclude copied stages, tokens = ceil(chars / 4) (spec: Metrics without an LLM)
- [ ] 6.2 Implement `summarise` and `main()` for `python -m evals.metrics --results DIR [--baseline NAME]` writing `metrics.json` and printing the Markdown table; verify a test over the replay results from 5.3 that the table has one row per variant and `metrics.json` has one entry per result

## 7. Judge

- [ ] 7.1 Add `evals/prompts/precision.md` (`$query` placeholder only) and implement `judge_result(llm, query, passages) -> float | None` in `evals/judge.py` with passages in a separate user message; verify tests with the fake LLM from `wosarcher.adapters.fakes`: answer `[0, 2]` over 4 passages gives 0.5, answer without a list gives None, and the user message contains the passage text unchanged (spec: Judged precision)
- [ ] 7.2 Implement `main()` for `python -m evals.judge --results DIR [--profile] [--set]` storing `judgements.jsonl` and skipping judged runs; verify a test (fake LLM injected by monkeypatching `build.build`) that a second call makes no LLM call

## 8. Documentation

- [ ] 8.1 Add an "Evals" section to docs/design.md (variants file, replay through `wosarcher fork`, metrics, judge, the recorded-run fixture and how to regenerate it) and add `evals/` contents to Package layout; verify the section matches the commands
- [ ] 8.2 Verify `scripts/check --full` passes and `openspec validate eval-replay --strict` passes

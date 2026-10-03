# Proposal

## Why

Choosing a prefilter or scorer (embeddings, BM25, rerank, Jev, thresholds)
should rest on measurements over the same inputs, as gpt-researcher's
`evals/context_filter` benchmark did. With run-orchestration every run is a
directory that `wosarcher fork` can replay from any stage, so search and
fetch, the noisiest parts, can be held constant while only the ranking
changes. The project also needs one end-to-end test of `wosarcher run` that
uses the real adapters against recorded responses, without live services.

## What Changes

- `evals/` package (outside `src/`, uses only the CLI and run files):
  - `evals/variants.toml`: named variants, each a fork stage (`prefilter` or
    `score`) plus `--set` overrides.
  - `python -m evals.replay`: forks every recorded run with every chosen
    variant through `wosarcher fork <id> --from <stage> --until select
    --json`, and records the fork IDs.
  - `python -m evals.metrics`: metrics with no LLM: kept passages, context
    characters and estimated tokens, seconds per stage, and overlap of the
    selected passages between variants (Jaccard), as JSON and a Markdown
    table.
  - `python -m evals.judge`: optional context precision judged by the
    configured `llm`: the share of selected passages rated relevant.
- A recorded-run fixture: `tests/fixtures/http/` (SearXNG, Firecrawl, and
  LLM response bodies), `tests/fixtures/profiles/e2e.toml`, and a committed
  run directory `tests/fixtures/runs/<id>/` produced from them by
  `tests/fixtures/make_recorded_run.py`.
- An end-to-end test of `wosarcher run` with the real adapters and respx,
  and replay, metrics, and judge tests over the fixture.

## Non-goals

- No benchmark dataset or committed benchmark results; the harness works on
  any set of recorded runs the user has.
- No pairwise report judging or SimpleQA grading (gpt-researcher's
  `judge.py` had both); variants stop at `select` by default, and report
  quality is out of scope here.
- No variant that changes search or fetch.
- No live service in any test.

## Capabilities

### New Capabilities

- `eval-replay`: replaying recorded runs with different prefilter and
  scorer settings, computing metrics without an LLM, optional LLM-judged
  precision, and the recorded-run fixture with its end-to-end test.

### Modified Capabilities

None.

## Impact

- New code: `evals/__init__.py`, `evals/variants.toml`, `evals/replay.py`,
  `evals/metrics.py`, `evals/judge.py`, `evals/prompts/precision.md`;
  `tests/fixtures/` (HTTP bodies, profile, recorded run, generator script);
  `tests/test_e2e_run.py`, `tests/evals/`.
- `pyproject.toml`: pytest `pythonpath = ["."]` and basedpyright `include`
  gains `evals`, so the harness is type checked and importable by tests.
- No new dependencies. `evals/` is outside `src/wosarcher`, so
  `scripts/check_architecture.py` does not apply; it imports
  `wosarcher.models`, `wosarcher.config`, and `wosarcher.build` only.
- Relies on run-orchestration: `wosarcher run`, `wosarcher fork`,
  `--json` (`RunOutput`), `--run-id`, `events.jsonl` with `stage.done`
  seconds, `context.json`, and provider-adapters' `build.build` (its `writer` LLM is the judge).
- docs/design.md sections implemented: Build order step 5 (recorded-run
  fixture and eval replay harness), Maintainability rules ("End-to-end test
  with fakes and a recorded run"), Commands (`fork` "used by the eval
  harness"). docs/design.md gains a short "Evals" section.

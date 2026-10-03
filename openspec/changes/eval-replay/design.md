# Design

## Context

run-orchestration provides `wosarcher run` and `wosarcher fork` with
`--json` (a `RunOutput` document), `--run-id`, `--until`, run directories
with `context.json` and `events.jsonl` (`stage.done` carries `seconds` and
`copied_from`); provider-adapters provides `build.build(settings, http, ledger) -> Adapters`.
provider-adapters provides the `searxng`, `firecrawl`, and `llm` adapters
and fakes; lexical-bm25 provides BM25 as prefilter and scorer, so a full run
needs no GPU or API. gpt-researcher's `evals/context_filter` (collect,
replay, judge) is the model: hold search and scraping constant, vary only
the filter, measure kept passages, size, time, and judged precision. See
proposal.md for motivation.

## Goals / Non-Goals

**Goals:**

- The harness drives the public CLI only, so it measures exactly what users
  run and needs no internal API.
- Metrics without an LLM are cheap enough to run on every replay.
- Tests run offline and fast.

**Non-Goals:**

- Statistical tests or plots. The Markdown table is the output; users can
  load the JSON elsewhere.
- Collecting new recorded runs: any `wosarcher run` is already a recording.

## Decisions

### Layout

```
evals/
  __init__.py
  variants.toml       # named variants
  replay.py           # python -m evals.replay
  metrics.py          # python -m evals.metrics (pure functions + main)
  judge.py            # python -m evals.judge
  prompts/precision.md
tests/
  fixtures/
    http/searxng/*.json      # one response body per query
    http/firecrawl/*.json    # one scrape response per URL
    http/llm/plan.json       # chat completion body for the planner
    http/llm/write.sse       # streamed chat completion for the writer
    profiles/e2e.toml        # hosts *.test, bm25 prefilter and scorer
    runs/20260101-000000-fixture/   # committed recorded run
    make_recorded_run.py     # regenerates runs/... from http/ and the profile
    recorded.py              # respx router built from http/ (shared by tests and the script)
  test_e2e_run.py
  evals/test_replay.py, test_metrics.py, test_judge.py
```

`evals/` is a plain package at the repository root (as in the design's
package layout). pytest gets `pythonpath = ["."]` and basedpyright includes
`evals`, so both import and type check it. It is outside `src/wosarcher`,
so the layering check does not apply; by convention it imports only
`wosarcher.models`, `wosarcher.config`, and `wosarcher.build`.

### Variants file

```toml
[bm25]
from = "score"
set = ["score.provider=bm25"]

[bm25-wide]
from = "score"
set = ["score.provider=bm25", "score.relative_threshold=0.3", "score.top_k=25"]

[rerank]
from = "score"
set = ["score.provider=rerank", "score.fallback=[]"]

[jev]
from = "score"
set = ["score.provider=jev", "score.fallback=[]"]

[prefilter-embeddings]
from = "prefilter"
set = ["prefilter.provider=embeddings"]

[prefilter-bm25]
from = "prefilter"
set = ["prefilter.provider=bm25"]
```

Model variants disable fallback so a broken service shows as a failed
result instead of silently measuring BM25. Parsed with `tomllib` into a
small Pydantic model `Variant(name, from_stage: Literal["prefilter",
"score"], set: list[str])`.

### Replay drives the CLI in a subprocess

```python
def fork(run_id: str, variant: Variant, *, write: bool, env: dict[str, str]) -> ForkResult:
    args = [sys.executable, "-m", "wosarcher", "fork", run_id, "--from", variant.from_stage, "--json"]
    if not write:
        args += ["--until", "select"]
    for item in variant.set:
        args += ["--set", item]
    done = subprocess.run(args, capture_output=True, text=True, env=env)
    ...  # parse RunOutput from stdout; on non-zero exit keep stderr tail as error
```

Results are JSON lines in `<out>/results.jsonl`: `{parent_run_id, variant,
run_id, status, error}`. Replay reads it first to skip finished pairs
(unless `--force`). Runs are given as run IDs or `--all` (every run in
`runs_dir` with `version == 1` and a finished `select` stage).
`runs_dir` comes from the normal configuration (`WOSARCHER_RUN__RUNS_DIR`
or `--set run.runs_dir=...` passed through), so the harness reuses the
CLI's resolution. Forks run one at a time: GPU variants must not compete,
and parallel forks would distort the timing metric.

Alternative: call `Runner.run` in process. Rejected: the CLI is the
contract the skill and server use, and a subprocess also isolates crashes.
Tests that need no network still use the subprocess (the `bm25` and
`bm25-wide` variants only).

### Metrics

Pure functions over a run directory, so they are unit tested on hand-made
directories:

```python
def selected_chunk_ids(run_dir: Path) -> list[str]
def context_size(run_dir: Path) -> tuple[int, int]            # chars, est. tokens = ceil(chars / 4)
def stage_seconds(run_dir: Path) -> dict[Stage, float]        # stage.done events without copied_from
def jaccard(a: set[str], b: set[str]) -> float                # 1.0 when both empty
def summarise(results: list[ResultMetrics]) -> str            # Markdown table, medians and p90
```

Characters divided by 4 is a deliberately simple, model-independent
estimate; the absolute number matters less than the comparison between
variants on the same runs. Output: `<out>/metrics.json` and the table on
stdout. Overlap is computed for every pair of variants that both finished
on the same parent run; the table shows each variant's median Jaccard
against `--baseline` (default: the first variant).

### Judge

`python -m evals.judge --results <out> [--profile NAME] [--set ...]`
resolves settings like the CLI, builds the ports with
`build.build`, and uses `adapters.writer.complete`. Messages:

1. system: `evals/prompts/precision.md`, filled with `string.Template`
   from the query only (a trusted value).
2. user: the numbered passages (`[i] text`, each cut to 1500 characters),
   inserted as a whole message, never templated.

The answer is parsed with the first `\[[\d,\s]*\]` match; indexes outside
the range are ignored; no match records `precision = None`. Judgements are
stored in `<out>/judgements.jsonl` keyed by fork run ID and skipped on
the next run. Concurrency is the `llm` block's own limit in
`ProviderClient`; the judge awaits results one result record at a time to
keep it simple. Usage is printed from the `UsageLedger` at the end.

### Recorded responses and fixture

`tests/fixtures/recorded.py` exposes `recorded_router() -> respx.Router`
with `assert_all_mocked=True` and `assert_all_called=False`:

- `GET http://searxng.test/search`: body chosen by the `q` parameter from
  `http/searxng/<slug(q)>.json`; an unknown query returns an empty result
  list.
- `POST http://firecrawl.test/v1/scrape`: body chosen by the `url` field
  from `http/firecrawl/<slug(url)>.json`; an unknown URL returns 404, which
  exercises `page.failed`.
- `POST http://llm.test/v1/chat/completions`: `plan.json` when the request
  is not streaming, `write.sse` when `stream` is true.

The paths and body shapes follow the searxng, firecrawl, and llm adapters
from provider-adapters; the fixture bodies are copied from real responses
of those services, trimmed to two sub-queries, four pages (one PDF-style
page, one failing URL), about 30 KB in total. The writer response cites
`[1]` and `[2]` only, so the citation check holds for any selection of at
least two passages.

`make_recorded_run.py` runs the CLI in process with `recorded_router()`
active, `--profile e2e`, `--run-id 20260101-000000-fixture`, and one
attachment `tests/fixtures/http/notes.md`, into `tests/fixtures/runs/`.
It is run by hand when contracts change; `test_fixture_parses` fails
first and names the artifact, which tells the developer to rerun it.

### End-to-end test

`test_e2e_run.py` sets `XDG_CONFIG_HOME` so `e2e.toml` is a user profile,
sets `WOSARCHER_RUN__RUNS_DIR` and `WOSARCHER_RUN__CACHE_DIR` to `tmp_path`,
activates `recorded_router()`, and invokes the typer app with `CliRunner`.
An unmatched request raises respx's `AllMockedAssertionError`, which names
the URL.

## Risks / Trade-offs

- [Fixture drifts from the contracts] → `test_fixture_parses` fails with
  the artifact name; regeneration is one command.
- [Adapter wire formats change in provider-adapters] → Fixture bodies are
  the recorded wire format; the e2e test is the place that catches it.
- [Subprocess per fork] → About 0.5 s start-up per fork; negligible next to
  a model scorer, acceptable for BM25 tests (four forks).
- [Characters/4 token estimate] → Not the writer's exact count. It is used
  only to compare variants on the same runs.

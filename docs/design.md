# wosarcher: design

A modular, scriptable research tool, inspired by gpt-researcher but split into
small parts with clear contracts. It is used three ways: from the CLI, from a
real-time WebSocket frontend, and by AI agents through a skill.

The CLI is `wosarcher`.

This document is the reference design. OpenSpec changes implement it one
capability at a time and may refine it; when they do, update this file.

## Goals

- Each stage does one job well and can be run alone.
- A core composes the stages through adapters; no god object.
- Scriptable: every stage reads and writes plain files, so runs can be
  forked, replayed, inspected with `jq`, and evaluated.
- Runs well on small GPUs (8 GB) and scales up to bigger machines or cloud
  providers through configuration only.
- Maintainable and human readable: small files, typed contracts, no magic.

## Non-goals (for now)

- Search providers besides SearXNG.
- Local PDF parsing. Firecrawl handles PDFs at URLs. Local PDFs are converted
  outside the tool (for example with pdf-ingest) and attached as markdown.
- Multi-agent orchestration, source curation, report chat. Deep (recursive)
  research is a later recipe.

## Pipeline

```
attachments ─► load ──────┬──────────────────────────────┐
                          │ outlines                     │
                          ▼                              ├─► pages ─► chunk ─► prefilter ─► score ─► select ─► write
query ─► initial search ─► plan ─► search ─► fetch ──────┘
```

Load runs before plan so the planner sees attachment outlines.

| Stage | Input | Output | Resource |
|---|---|---|---|
| plan | query, initial search snippets, attachment outlines | sub-queries | LLM |
| search | sub-queries | hits (URL, title, snippet, query IDs) | network |
| fetch | hits | pages (markdown) | network |
| load | attachment bytes | pages, outlines | CPU |
| chunk | pages | chunks with heading path | CPU |
| prefilter | chunks, queries | top-K (query, chunk) pairs | GPU or API |
| score | pairs | scores | GPU or API |
| select | scores | context within a token budget | CPU |
| write | context, query, writing options | report with citations | LLM |

### Initial search

Kept from gpt-researcher: one SearXNG call with the main query before
planning, so the planner sees real result titles and snippets, not only the
query. Snippets are short and come from SearXNG, not from scraped pages, so
fetched content never reaches the planner.

### Dedupe

- URLs are normalised (scheme, host case, trailing slash, tracking
  parameters, fragments) and fetched once per run, even when several
  sub-queries find them. A hit records every query ID that found it.
- Chunks with the same normalised-text hash are kept once.

### Small-input passthrough

When all pages for a query total less than `select.passthrough_chars`
(default 8000), they skip prefilter and score: every pair is kept with
`passthrough` scores, whatever scorer the run uses. Applies to web and
files.

### GPU use

Stages run as phases across all sub-queries, not per sub-query. Search and
fetch are concurrent. GPU stages (prefilter, score, write on a local LLM) run
one after another, each in large batches.

### Endpoints and devices

Every model provider is an HTTP endpoint, so a model can run on this machine
or on another machine in the local network; the pipeline does not care. Each
provider block names its endpoint and, optionally, the device it runs on:

```toml
[prefilter]
provider = "embeddings"
base_url = "http://desktop.lan:8002/v1"
device = "desktop:gpu0"        # free-form label; omit for cloud or CPU

[score]
provider = "rerank"
base_url = "http://desktop.lan:8001/v1"
device = "desktop:gpu0"
release = "llama-swap"         # none | llama-swap | ollama

[llm]
base_url = "http://localhost:8080/v1"
device = "laptop:gpu0"
```

`base_url` includes the API version (`/v1`, or `/v2` for Cohere), as in
OpenAI-compatible clients; each adapter appends a fixed resource path (see
Adapters). Unload and health calls go to the **server root**: `base_url`
without a trailing `/` and then without a trailing `/v1`, for the primary
URL and each fallback URL.

`run.gpu_policy`:

- `shared` (default): models stay resident; this works with plain
  llama-server when the models fit.
- `exclusive`: after a GPU stage, the runner releases its model only if the
  next GPU stage that runs uses the **same device label** and a different
  block (`plan` and `write` use `llm`, `prefilter` uses `prefilter`, `score`
  uses `score`). It emits `resource.waiting` for that next stage, calls
  `release()`, then emits `resource.released`; a release error becomes a
  warning on the next `stage.done`. A block with `release = "none"` is never
  released. On cancellation the current GPU stage's model is released. Stages on different devices
  (for example the reranker on the desktop and the writer on the laptop)
  never wait for each other. Release needs a backend that can unload,
  called over HTTP so it works for remote hosts too: llama-swap
  (`GET <root>/unload`, which unloads every model on that server) or Ollama
  (`POST <root>/api/generate` with the block's `model` and `keep_alive: 0`;
  `release = "ollama"` requires `model`). Plain llama-server has no unload
  endpoint; `wosarcher doctor` warns when a block that cannot unload shares
  its device with another block.

There is no separate scheduler: stage order already serialises GPU use, and
device labels decide when a release is needed.

Remote endpoints:

- **Config only.** Machines are named by URL in a profile; no discovery
  service. A typical setup is one profile per machine, for example
  `laptop.toml` pointing embeddings and reranker at the desktop.
- **Failover.** `fallback_urls` lists other endpoints serving the same model,
  tried in order when the first is unreachable. Load balancing across hosts
  is out of scope; put LiteLLM or llama-swap in front if needed.
- **Timeouts and batches.** Connect timeout short (`connect_timeout`, 3 s) so
  a sleeping machine fails fast and the fallback chain takes over (BM25 for
  prefilter and score). Larger batches amortise network latency.
- **Payload size.** Request `encoding_format: "base64"` for embeddings when
  the server supports it; JSON float arrays are several times larger.
- **Security.** Run llama-server with `--api-key` and bind to the LAN
  interface or a VPN such as Tailscale, not to all interfaces. The `api_key`
  field of each provider block carries the key.
- **Cache correctness.** The embedding cache key is content SHA-256 plus the
  model name reported by the endpoint plus vector dimension, so pointing at a
  different machine with a different model never reuses wrong vectors. The
  runner reads model and dimension from `embedder.describe()` once before
  the prefilter stage; when that fails it passes no cache. Vectors live in
  `<cache_dir>/embeddings/<model>/<dim>/<sha[:2]>/<sha>.f32` (raw float32).
- **Health.** `wosarcher doctor` checks each endpoint: reachable, model name,
  latency of one small request, unload support (llama-swap answers
  `GET <root>/running`, Ollama `GET <root>/api/version`).

### Scoring

- A score is always for a pair: `Score(query_id, chunk_id, value, scorer)`.
- Web chunks are paired with every query that found their page.
- File chunks are paired with the main query and each sub-query. Only
  pairs that survive the prefilter (`prefilter.top_k` per query, default
  50, by embedding similarity or BM25, or all with `none`) reach the
  scorer. If the embedder fails, the prefilter uses BM25 for the whole
  stage and records a warning. Embeddings are cached by the SHA-256 of the
  text.
- Each scorer declares whether its scores are calibrated:
  - `jev`: calibrated 0 to 3; absolute threshold `score.min_score`
    (default 1.5).
  - `rerank`: not calibrated across queries; relative threshold
    `score.relative_threshold` (keep pairs scoring at least this fraction of
    the best pair for the same query, default 0.5). When no score of a
    query is positive, only its best pair is kept.
  - `bm25`: local, no model, no API; raw BM25 values, kept by the lexical
    ranking rule: relative threshold (default 0.5), zero scores dropped, up
    to 25 chunks per query, and the first chunks in page order when nothing
    matches.
  - `passthrough`: values `len - i` in search-rank, page, position order,
    so that order is kept; every pair is kept.
- After thresholds, every chunk (web or file) keeps only its best pair
  across queries (highest display score, ties to the earlier query); that
  query is its best query ID, so per-query quotas still work and no chunk
  is selected twice.
- Then every scorer except `passthrough` is capped at `score.top_k` per
  query (default 10).

**BM25** is pure Python with no dependencies (`wosarcher/lexical.py`, about 100
lines, modelled on gpt-researcher's `gpt_researcher/context/lexical.py`):
Unicode word tokens, English stopwords removed, light plural stemming,
k1 = 1.5, b = 0.75, IDF over the query's own chunks. Three functions:
`tokenize(text)`, `bm25_scores(query, texts)`, and `rank(query, texts)`,
which returns kept positions best first (relative threshold 0.5, at most 25
results). If no chunk matches any query term, or the query has only
stopwords, `rank` returns the first texts in the order given (callers pass
chunks in search-rank, then page order). In gpt-researcher's benchmark
it kept 51% relevant passages against 46% for embeddings, in about 20 ms per
sub-query.

BM25 has three roles:

- **Scorer** when no GPU or API is available (`score.provider = "bm25"`).
- **Prefilter** when no embedding model is configured
  (`prefilter.provider = "bm25"`), so the reranker or Jev still sees a
  bounded candidate set.
- **Fallback** for the scorer.

**Fallback is per stage, not per call.** The chain lives inside the score
stage. If any call of the configured scorer fails, the whole score stage
reruns with the next scorer in `score.fallback` (default
`["bm25", "passthrough"]` after the configured one; only these two built-in
scorers are allowed, because the score block configures one remote
endpoint), so one run never mixes
score scales. The terminal fallback is `passthrough`: chunks in search-rank
order, then page order, capped by the token budget. A run never ends without
context. The runner reports what the stages did: one `stage.failed` per
scorer that failed (with the scorer that ran next) and `stage.done.provider`
naming the scorer or prefilter method that actually ran. The prefilter falls
back from embeddings to BM25 the same way, inside its stage.

### Select

Order of rules:

1. Scorer threshold.
2. Per-source cap (`select.max_chunks_per_source`).
3. Round-robin across queries, best score first, until the token budget is
   full.

The per-source cap (default 5) keeps a source's passages ranked highest
within their own query. Round-robin takes one passage per query per round,
in plan order; a passage that does not fit is skipped and the next is
tried.

The token budget is
`min(select.max_context_tokens, llm.context_window - select.prompt_reserve_tokens - output)`,
where `output = max(1024, 2 * words)` is also the write call's
`max_tokens` (defaults 16000 and 2000). A budget of zero or less is an
error naming `llm.context_window`.

File and web shares are soft and run in two phases: when both sides have
passages, files first get `floor(select.file_share * budget)` (default
0.5) and the web the rest; then the passages left on both sides share
whatever budget is unused, by the same round-robin. `--sources files` uses
the whole budget. Passages are numbered `1..N` in the order taken.

### Attachments

- `wosarcher run "q" --attach notes.md --attach ./docs/` (files, directories, globs).
  `attachments.py` expands the paths (directories recursively in sorted
  order, hidden parts skipped) and reads the bytes; a path that matches
  nothing fails the run before any stage. The load stage only sees bytes,
  so the server can pass uploads without touching disk.
- Formats: `.md` and `.txt`; other files in a directory are skipped with a
  warning. UTF-8 with replacement; size limit `attach.max_bytes`. Identical
  content is loaded once. No page cap: `fetch.max_chars` is for web pages
  only.
- pdf-ingest output is detected by its `<!-- page: … -->` and `<!-- a: … -->`
  comments; chunks keep page and block IDs for citations.
- The planner sees an outline of each attachment (headings plus the first
  lines of each section) and writes sub-queries for the gaps.
- `--sources files|web|both` (default `both`). `files` means document Q&A
  with no search.
- Embeddings for attachment chunks are cached by content SHA-256.
- Attachments are copied into the run directory so a run is self-contained.

### Chunking

Markdown-aware: split by headings, then by size (`chunk.size` 1000
characters, `chunk.overlap` 100). Each chunk keeps its heading path. HTML
comments, images (kept as alt text), link URLs (kept as link text), and
autolinks are stripped from chunk text. pdf-ingest anchors become chunk
metadata: `page_id` is the page in effect at the chunk start and
`block_ids` the `<!-- a: … -->` anchors inside it; the anchors are removed
from the text. The Fetcher cuts web pages at `fetch.max_chars` (50000) and
marks them truncated; the fetch stage never cuts again.

### Writing options

Global defaults in config, overridable per run from the CLI, the server
request, or the skill. Runs started by the server also apply the server's
global settings (see Server) between the profile and the request.

| Option | Default | Values |
|---|---|---|
| `tone` | `objective` | objective, formal, analytical, persuasive, informative, explanatory, descriptive, critical, comparative, speculative, reflective, or a custom entry in `prompts/tones.toml`; case-insensitive |
| `tone_instructions` | empty | free text added to the tone, for one-off styles |
| `words` | 1200 | target length |
| `language` | english | report language |
| `citation_marker` | numeric | numeric (`[1]`), superscript, author-year: how citations appear in the text |
| `reference_style` | APA | APA, MLA, Chicago, IEEE (case-insensitive): how the reference list is formatted |

Tones are data, not code: `prompts/tones.toml` maps each name to its
description (the gpt-researcher list is the starting set). A custom tone is
one more entry in that file. The write stage checks `tone` against that file
and `reference_style` against the four known styles before calling the LLM;
an unknown name fails with the list of known names.

Writing options affect only the write stage, so changing them on a finished
run is cheap: `wosarcher fork <id> --from write --tone critical` reuses all context
and only rewrites the report.

### Citations

Citations point to passages, not sources, so a reader can see the exact text
behind each claim.

- Each selected passage gets a number `n` in `context.json`, mapped to its
  `chunk_id` and its `source_id`.
- The writer cites with `[n]`. Code renders the marker in the chosen
  `citation_marker` style.
- After writing, the write stage checks that every `[n]` exists. Each
  unknown number is a warning and is removed from the rendered report; a
  report that cites no passage gets a warning. `[n](url)` is a link, not a
  citation.
- `Report.body` keeps the raw `[n]` markers as streamed (for the frontend's
  hover); `Report.markdown` holds the rendered markers and the reference
  list.
- The reference list (`## References`) lists each cited source once, in
  order of first citation for every style, formatted by code in the chosen
  `reference_style`. Under each source, its cited passages are listed with
  their heading path, or `p. <page ID>` and block IDs for pdf-ingest files.

### Prompt injection

- Fetched content never reaches the planner.
- The writer receives chunks in a separate, delimited message and is told to
  treat them as data, not instructions.
- Scraped text is never passed through `str.format` or a template engine;
  it is inserted as a whole message.

## Adapters

| Port | Adapter | Local | Cloud |
|---|---|---|---|
| Port | Adapter | Path after `base_url` | Default concurrency | Local | Cloud |
|---|---|---|---|---|---|
| Searcher | `searxng` | `GET /search` | 4 | self-hosted | any SearXNG URL that allows `format=json` |
| Fetcher | `firecrawl` | `POST /scrape` | 6 | self-hosted (`http://host:3002/v1`) | `https://api.firecrawl.dev/v1` |
| Embedder | `embeddings` (OpenAI-compatible) | `POST /embeddings` | 4 | llama-server, Ollama, vLLM | OpenAI, Jina, Voyage |
| Scorer | `rerank` (Cohere/Jina-style) | `POST /rerank` | 4 | llama-server `--rerank`, vLLM | Jina, Cohere, Voyage |
| Scorer | `jev` | `POST /systemone` | 64 | none | TypeSafe (`https://api.typesafe.ai/v1`) |
| Scorer, Prefilter | `bm25` (built in, `wosarcher/lexical.py`) | none | none | CPU | none |
| Scorer | `passthrough` (built in) | none | none | CPU | none |
| LLM | `llm` (OpenAI-compatible chat) | `POST /chat/completions` | 1 | llama-server, Ollama | any |

One adapter per wire format, not per vendor: `base_url` and `api_key` select
the provider. Every adapter has a fake for tests.

Provider settings that matter: `search.max_results` (10), `search.language`,
`search.time_range` (`day`, `week`, `month`, `year`); `fetch.only_main_content`,
`fetch.page_timeout` (45 s, must be below `fetch.timeout`; PDFs are slow),
`fetch.max_chars` (50000). An unset `concurrency` takes the adapter default
above; the planner and writer share one LLM client and its limit.

Every remote adapter also has `probe()` (one small request, for
`wosarcher doctor`) and `release()` (unload as configured by `release`; a
no-op for SearXNG and Firecrawl).

## Architecture

Ports and adapters. Stages are pure functions over models and ports. The
runner owns persistence and events. Interfaces sit at the edge.

```
cli/ ── server/ (spawns `wosarcher run`, tails events.jsonl and report.md) ── skill (CLI + SKILL.md)
   │
runner/  ── store/ (runs/<id>/) ── events.jsonl
   │
stages/  plan search fetch load chunk prefilter score select write   (pure)
   │ ports.py (Protocols)
adapters/  searxng firecrawl embeddings rerank jev llm  ── http.py
```

### Package layout

```
src/wosarcher/
  models.py      # Pydantic contracts (Stage, RunRequest, Query, Plan, Hit, Source, Page, Chunk, Attachment, Skipped, stage results, Score, Context, Report, WritingOptions, Message, Completion, EmbedderInfo, ProviderHealth, DoctorReport, RunRecord, RunSummary, RunOutput, RunCosts, server API bodies, events) and ID helpers
  ports.py       # Protocols: Searcher, Fetcher, Embedder, Scorer, LLM, Managed; the Adapters bundle
  config.py      # settings, profiles, precedence, secret redaction
  auth.py        # password hashing, API tokens, session signing, auth.json (AuthStore); stdlib only, no FastAPI
  http.py        # ProviderClient: retry with backoff, fallback URLs, per-provider semaphore, SSE streams; unload; UsageLedger
  profiles/      # built-in low-vram.toml, workstation.toml, cloud.toml
  store/         # __init__.py: RunStore (create, fork, artifacts, events.jsonl with seq, list_runs); caches.py: PageCache, EmbeddingCache
  runner/        # __init__.py: Runner (stage loop, timeouts, costs, cancel); steps.py: one function per stage;
                 # events.py: EventLog, snapshot_event; devices.py: needs_release; caches.py: CachedFetcher, EmbeddingMapping
  build.py       # composition root: config -> adapters (a dict, no registry)
  doctor.py      # provider health probes and exclusive-GPU warnings
  lexical.py     # BM25: tokenizer, scoring, relative threshold (pure functions)
  attachments.py # expands --attach paths and reads the files' bytes (the only attachment file I/O)
  stages/        # one file per stage
  adapters/      # one file per adapter, plus fakes.py
  prompts/       # __init__.py (load(name) -> string.Template from package data), jev.toml, plan.md, plan_data.md, write.md, passages.md, write_task.md, tones.toml (tones())
  cli/           # __init__.py: typer app (profile, doctor, schema); run.py: run, fork, runs; serve.py: serve; auth.py: auth; progress.py: rich Live view
  __main__.py    # python -m wosarcher
  server/        # __init__.py: create_app; manager.py: RunManager (queue, subprocesses, cancel); staging.py: runs/.queue/ and argv;
                 # tail.py: RunTail; routes.py: /api/runs; meta.py: settings, profiles, health; stream.py: event socket;
                 # settings.py: server-settings.json; errors.py: JSON errors; state.py: ServerState;
                 # guard.py: request guard; login.py: login, logout, session; limiter.py: LoginLimiter; tokens.py: /api/tokens
skill/SKILL.md
evals/
  variants.toml  # named ranking variants: fork stage (prefilter or score) plus --set overrides
  replay.py      # python -m evals.replay: forks recorded runs per variant through `wosarcher fork`
  metrics.py     # python -m evals.metrics: passages, context size, stage seconds, Jaccard overlap
  judge.py       # python -m evals.judge: precision judged by the configured llm
  prompts/       # precision.md
tests/
  fixtures/      # recorded HTTP bodies (http/), profiles/e2e.toml, recorded.py (respx router),
                 # runs/20260101-000000-fixture/ and make_recorded_run.py that regenerates it
```

### Patterns used, and only these

- **Ports and adapters.** Stages depend on `Protocol`s, never on adapters.
- **Composition root.** `build(config)` creates adapters from a dict of
  constructors. No registry, no globals.
- **Pure stages.** `plan(query, snippets, outlines, llm) -> Plan`. A stage
  gets its inputs and ports, returns its output, and does not know about
  files or events. Tests need only fakes.
- **Repository.** `RunStore` owns paths and serialisation.
- **Append-only event log.** `RunStore.append_event` assigns `seq` (last
  logged plus 1, also for another process appending later) and writes the
  event to `events.jsonl`; the runner then publishes it.

Cross-cutting concerns (retry, rate limits, costs) live in `http.py` as
plain functions used by adapters, not as generic decorators.

Prompt templates: Markdown files with `{placeholders}` filled only from
trusted values (query, options). Scraped text never goes through templates.

### Run directory

```
runs/<id>/
  request.json       # RunRecord: request, profile, overrides, resolved config (secrets "***"), lineage
  attachments/       # copies of --attach files, directories, and globs
  files.jsonl        # load: attachment pages
  plan.json          # plan
  initial.jsonl      # plan: hits of the initial search for the main query
  hits.jsonl         # search: all hits, initial ones merged in
  pages.jsonl        # fetch: web pages
  chunks.jsonl
  candidates.jsonl
  scores.jsonl
  context.json
  report.md          # written as the report streams, then replaced by the rendered report
  report.json        # the structured Report
  events.jsonl
  costs.json         # usage and cost per stage, per provider, and in total
```

`runs_dir` defaults to `$XDG_DATA_HOME/wosarcher/runs` (`run.runs_dir`);
caches live in `$XDG_CACHE_HOME/wosarcher` (`run.cache_dir`): fetched pages
by normalised URL for `run.page_cache_ttl_hours` (24; 0 disables) and
embeddings. Run IDs are `YYYYMMDD-HHMMSS-xxxxxx` and sort by creation time.
Directories starting with `.` (the server's `.queue/`) are not runs.

A stage is finished when its `stage.done` event is in `events.jsonl`; a
half-written artifact without that event is ignored. Artifacts are written
to `<name>.tmp` and renamed. A stage skipped by `--sources` writes empty
artifacts and a `stage.done` with `skipped`. Each stage has a timeout in
`run.stage_timeouts`.

### Commands

- `wosarcher run "q" [--attach ...] [--sources ...] [--until select] [--tone ...] [--words ...] [--run-id ID] [--json]`:
  writing flags act as `--set write.<field>=...` after the `--set` values.
  `--run-id` lets a caller (the server) choose the ID; an existing directory
  exits 2. `--json` prints one `RunOutput` document (status, error, run
  directory, context when select finished, report when write finished). On a
  terminal, progress goes to standard error; piped output is the report
  Markdown. Exit status: 0 done, 1 failed, 130 cancelled (SIGTERM, SIGINT),
  2 invalid arguments or configuration.
- `wosarcher fork <id> --from <stage> [overrides] [--profile NAME] [--until ...] [--run-id ID] [--json]`:
  copies `attachments/` and the artifacts before `<stage>` into a new run
  (version parent plus one), logs a copied `stage.done` per earlier stage,
  and continues with the saved config (secrets taken from the current
  environment) plus the overrides. With `--profile`, settings come from that
  profile plus the parent's and the new overrides. Used for resume, for
  changing writing options, and by the eval harness.
- `wosarcher doctor [--profile <name>] [--set k=v] [--json]`: one row per
  block (provider, base URL, device, status, model, latency, unload support);
  built-in scorers are shown without a request. Warns about blocks that
  cannot unload. Exit code 1 when any probe fails. The Firecrawl probe
  scrapes `https://example.com`, which spends one credit on the cloud API.
- `wosarcher runs [--limit N] [--json]`: lists runs newest first as
  `RunSummary` rows, with status from the last `run.*` event: `done`,
  `failed`, `cancelled`, or `interrupted` (started without an end), plus
  `until`, `fork_from`, the resolved writing options, `duration_s`
  (`run.started` to the terminal event), and `cost` (from `costs.json`).
- `wosarcher serve [--host H] [--port P]`: the HTTP server (see Server);
  binds `server.host` and `server.port` (`127.0.0.1:8765`).

### Events

- Run: `run.queued` (server only, live), `run.started`, `run.done`, `run.failed` (stage and
  error text), `run.cancelled`.
- Stage: `stage.started`, `stage.progress` (counters), `stage.done` (with
  cost), `stage.failed` (error text).
- Resources: `resource.waiting` (stage waits for a device, for example while
  the previous model unloads), `resource.released`.
- Plan and search: `plan.ready` (sub-queries), `hit.found` (URL, title,
  query IDs).
- Fetch: `page.fetched`, `page.failed` (reason).
- Score: `passages.scored`, one per query: counts, the scorer that actually
  ran, and the kept passages (text, heading path, source, display score).
  The full list, including rejected passages, is the `scores.jsonl`
  artifact.
- Write: `report.delta` and `report.snapshot` (server only, live).

Each event: `{seq, run_id, ts, type, stage?, data}`. Event models live in
`models.py` and are part of `wosarcher schema`. `data` fields:

| Type | `data` |
|---|---|
| `run.queued` | `position` |
| `run.started` | `query`, `profile`, `parent_run_id`, `version`, `until` |
| `run.done` | `until`, `totals` |
| `run.failed` | `stage`, `error` |
| `run.cancelled` | `stage` |
| `stage.started` | `device`, `provider` |
| `stage.progress` | `done`, `total`, `failed` (at most every 250 ms, plus a final one) |
| `stage.done` | `count`, `seconds`, `usage` (`UsageTotals` with `cost`), `provider`, `skipped`, `copied_from`, `warnings` |
| `stage.failed` | `error`, `next` (empty when none) |
| `resource.waiting`, `resource.released` | `device`, `released_stage` |
| `plan.ready` | `queries` |
| `hit.found` | `url`, `title`, `query_ids` |
| `page.fetched` | `url`, `source_id`, `title`, `chars`, `cached` |
| `page.failed` | `url`, `reason` |
| `passages.scored` | `query_id`, `scorer`, `scored`, `kept`, `threshold_display`, `passages` (`KeptPassage`) |
| `report.delta`, `report.snapshot` | `text` |

`seq` is assigned by the store's append, so the log has no gaps.
`run.queued`, `report.delta`, and `report.snapshot` are live only and never
written to `events.jsonl`; on the socket they carry the last logged `seq`
sent to that client (0 when none). The report text is appended to
`report.md` as it streams and replaced by the rendered report at the end of
the write stage. A reconnecting client gets all logged events after its
`seq`, then a `report.snapshot` of the report so far, then live events; when
the report changes other than by appending, clients get a new
`report.snapshot` instead of a delta.

### Errors and cancellation

- Per-item failures (one search, one page, one scorer batch) are logged and
  the stage continues.
- A stage fails the run only when its output is empty and no fallback is
  left (for example zero pages fetched with `--sources web`).
- Each stage has a timeout.
- Cancel cancels the asyncio task; in-flight HTTP requests are cancelled,
  `release()` is called in `exclusive` mode, and `run.cancelled` is emitted.

### Costs

Adapters add usage to a `UsageLedger` (per provider and stage): LLM and embedding tokens, Jev input
tokens, Firecrawl credits. A stage's usage is the ledger total after minus
before the stage (stages never overlap); `stage.done` carries it. The runner
writes `costs.json`: `{"stages": {...}, "providers": {...}, "total": ...}`,
each a `UsageTotals` with `cost` in dollars.

### Server

The server spawns `wosarcher run` (or `wosarcher fork`) as a subprocess per
run with a server-chosen `--run-id` and tails `events.jsonl` and
`report.md` every 100 ms, so the CLI, the server, and the skill share one
code path. It never runs stages itself. Every JSON route and the event
socket live under `/api`, so frontend routes like `/runs/<id>` never
collide with them. Errors are `{"error": code, "detail": text}`; an unknown
run is 404 `run_not_found`, an invalid body 422 naming each field.

- `POST /api/runs` (multipart: a `request` field with `RunCreate` JSON plus
  `attachments` files, reduced to their base names; duplicates are 422)
  returns 201 with `run_id` and `queued` or `running`.
- `GET /api/runs`, `GET /api/runs/{id}`: `RunSummary` (status `queued`,
  `running`, `done`, `failed`, `cancelled`, `interrupted`; lineage;
  `until`; resolved writing options; `duration_s`; `cost`;
  `queue_position`), and for one run `RunDetail` (plus the redacted
  `request.json`, `costs`, `last_seq`).
- `GET /api/runs/{id}/artifacts/{name}`: only `request.json`,
  `files.jsonl`, `plan.json`, `initial.jsonl`, `hits.jsonl`, `pages.jsonl`,
  `chunks.jsonl`, `candidates.jsonl`, `scores.jsonl`, `context.json`,
  `report.md`, `report.json`, `events.jsonl`, `costs.json` (JSON as
  `application/json`, JSONL as `application/x-ndjson`, Markdown as
  `text/markdown`, UTF-8); anything else is 404.
- `POST /api/runs/{id}/cancel`: SIGTERM for a running run (202; SIGKILL
  after 10 s, then the server logs `run.cancelled`), removal for a queued
  one (200, connected clients get `run.cancelled`), 409 otherwise.
- `POST /api/runs/{id}/fork` (`from`, optional `writing`, `set`,
  `profile`): `wosarcher fork` through the queue. A fork keeps the parent's
  configuration: only the request's writing fields and `set` are passed,
  not the global settings. 409 for a queued or running parent or an
  unfinished earlier stage; 422 for an unknown stage.
- `POST /api/runs/{id}/rerun`: a new run (version 1, no parent) with the
  original query, sources, `until`, profile, and saved overrides, and a
  copy of its `attachments/`; global settings are not applied. 404 for an
  unknown run, 409 for a queued one.
- `WS /api/runs/{id}/events?since=<seq>`: replays logged events after
  `seq`, sends a `report.snapshot` when the report is not empty and
  `run.queued` while queued, then live events and `report.delta` until a
  terminal event, and closes with 1000. Unknown runs close with 4404; a
  client more than 1000 events behind is closed with 4408 and reconnects
  with `since`. Runs not owned by this server (finished, interrupted, or
  started by the CLI) are replayed and closed.
- `GET /api/settings` and `PUT /api/settings`: global defaults
  (`ServerSettings`: all writing options and `sources`), stored in
  `<config dir>/server-settings.json`. They apply only to runs started by
  the server, as `--set write.*` values after the profile and before the
  request's `writing` and `set` (request wins). CLI runs use the profile.
- `DELETE /api/runs/{id}`: 204 for a finished run or a queued one, 409
  `run_active` for a running one.
- `GET /api/profiles`: `name`, `source` (`builtin` or `user`), `active`.
- `GET /api/providers/health[?profile=P]`: runs `wosarcher doctor --json`
  (60 s timeout; 502 when it times out or prints no report) and maps each
  row: failed is `down` (error as detail), built in is `skipped`, a model
  that cannot unload or a probe over 1000 ms is `degraded`, else `ok`.
- `POST /api/login`, `POST /api/logout`, `GET /api/session`
  (`SessionInfo`): see Authentication.
- `GET /api/tokens` (`TokenInfo`: ID, name, masked last 4 characters,
  created, last used; never the token or its hash), `POST /api/tokens`
  with `{"name"}` (201 `TokenCreated`, the only time the token is shown),
  `DELETE /api/tokens/{id}` (204, or 404 `token_not_found`). They need a
  browser session (or disabled authentication); a request authenticated by
  a token gets 403.
- When `server.static_dir` (`web/dist`) exists, the frontend build is
  served at `/`, and any other `GET` outside `/api` answers `index.html`.

Request and response bodies (`RunCreate`, `ForkCreate`, `RunCreated`,
`RunSummary`, `RunDetail`, `ServerSettings`, `ProfileInfo`,
`ProviderCheck`, `HealthReport`, `ApiError`, `LoginRequest`,
`SessionInfo`, `TokenInfo`, `TokenCreate`, `TokenCreated`, `LoginError`) are models in `models.py` and
part of `wosarcher schema`.

Runs record lineage: `parent_run_id` and `version` (1 for a new run, parent
version plus one for a fork) and `fork_from` (the stage a fork started
from), which the Versions screen shows. Rerun is a new run (version 1, no
parent) with the same request and attachments; "Retry from Score" is a
fork from the score stage.

`server.max_concurrent_runs` (default 1) limits run processes; further runs
wait in FIFO order and get `run.queued` with their position (1 is next).
A queued run is staged in `runs/.queue/<id>/` (request and attachments)
until its process starts, and staged runs are queued again in creation
order when the server starts. When a process exits without a terminal
event, the server appends `run.failed` with the exit code and the last 20
lines of standard error. On shutdown the server sends SIGTERM to every run
process and waits up to 10 s; queued runs stay staged. Settings:
`server.host`, `server.port`, `server.max_concurrent_runs`,
`server.static_dir`.

### Authentication

One admin user, for local use: it keeps everyone but the owner out when the
server is reachable from other devices. No accounts, roles, or sign-up.
Authentication is enabled when a password hash is configured; without one,
every request counts as authenticated (`method = "none"`) and the server
stays loopback only.

- **Bind.** The server binds to `127.0.0.1` by default. `wosarcher serve`
  refuses (exit code 2) any host that is not loopback (`127.0.0.0/8`,
  `::1`, `localhost`) unless a password is set.
- **Password.** `wosarcher auth set-password` prompts twice for a password of
  at least 8 characters and stores only its scrypt hash
  (`hashlib.scrypt`, n = 2^15, r = 8, p = 1, 32-byte key, 16-byte salt, as
  `scrypt$15$8$1$<salt>$<key>`) with a new session secret.
  `set-password --print` prints the hash for
  `WOSARCHER_AUTH__PASSWORD_HASH` instead of storing it; that variable (or
  `auth.password_hash` in a profile) wins over the stored hash, and
  `set-password` warns when it is set. The plain password is never stored
  or logged.
- **`auth.json`** in the config directory (mode 0600) holds the password
  hash, the session secret, and the API tokens (ID, name, SHA-256 hash,
  last 4 characters, created, last used). The server reloads it when its
  modification time changes, so CLI changes apply without a restart;
  writers lock `auth.json.lock` and replace the file atomically.
- **Browser session.** `POST /api/login` with `{"password"}` sets the
  `wosarcher_session` cookie and answers 200 with the session; a wrong
  password answers 401 `wrong_password` with `attempts_left`; 409
  `auth_disabled` when no password is set. The cookie holds a random
  token, its issue and expiry times, and an HMAC-SHA256 signature keyed by
  the session secret and the password hash; it is `HttpOnly`,
  `SameSite=Strict`, `Path=/`, `Secure` when the request arrived over
  HTTPS, and lasts `auth.session_days` (30). `POST /api/logout` clears it
  (204). `GET /api/session` says how the request is authenticated
  (`cookie` with `since` and `expires`, `token` with its name, or `none`).
  Changing the password ends every session; API tokens stay valid.
- **Brute force.** Failed logins are counted per client IP: the fifth
  failure within 60 seconds pauses logins from that IP for 30 seconds, and
  each further pause doubles, up to 15 minutes. While paused, every login,
  even with the right password, answers 429 `rate_limited` with
  `retry_after` and a `Retry-After` header. A successful login, or 15
  minutes without a failure, resets the count and the pause. Each failure
  is logged with the client IP. The limiter lives in memory.
- **Scripts and agents on other machines.** `Authorization: Bearer <token>`
  with a token (`wosarcher_` plus 36 base62 characters) from
  `wosarcher auth new-token <name>` or `POST /api/tokens`, stored as a
  SHA-256 hash; `wosarcher auth list-tokens` and `revoke-token <id>`. Each
  use updates the token's last-used time at most once a minute. The local
  CLI and the skill run `wosarcher` directly and need no auth.
- **Request guard.** One ASGI middleware checks every `/api` request and
  the event WebSocket, in order:
  1. **Host**: without a password, the `Host` name must be `localhost`,
     `127.0.0.1`, or `[::1]` (any port), else 403 `bad_host`, so a
     DNS-rebound page cannot reach the open API.
  2. **Origin**: on `POST`, `PUT`, `PATCH`, `DELETE`, and WebSocket
     handshakes, an `Origin` header, when present, must equal the server's
     own origin (request scheme and `Host`) or be in
     `auth.allowed_origins`, else 403 `bad_origin`. Browsers always send
     it on cross-site requests, which blocks CSRF and cross-site WebSocket
     hijacking.
  3. **Content type**: state-changing requests with a body must be
     `application/json`, and `POST /api/runs` `multipart/form-data`, else
     415 `unsupported_media_type`.
  4. **Authentication**: a valid bearer token or session cookie, except
     for `POST /api/login`, else 401 `unauthenticated`.
  5. **Token routes**: `/api/tokens` with a token gets 403.

  A refused WebSocket handshake is closed with 1008 before it is accepted.
  The frontend build (including `/login`) is served without
  authentication.
- **Transport.** On plain HTTP over Wi-Fi, the password and cookie can be
  sniffed. Use Tailscale (encrypted, and limits access to your devices) or a
  local reverse proxy with TLS (for example Caddy). The server must not be
  exposed to the internet. Behind a local proxy, uvicorn's proxy headers
  supply the client IP and scheme.

Settings: `auth.password_hash`, `auth.session_days`, `auth.allowed_origins`.

### Configuration

Precedence: built-in defaults < profile < environment < CLI flags or request
fields. The profile name itself is read from the CLI or environment first,
then the profile loads. `config.resolve(profile, overrides, env)` does the
whole resolution in one function and validates once; errors name the source
of the bad value (profile file, environment variable, or `--set` override).

Environment variables use the prefix `WOSARCHER_` and `__` for nesting
(`WOSARCHER_SCORE__API_KEY`). `--set` values are parsed as TOML values, so
`--set score.top_k=12` is an integer.

Each provider block has the same shape: `provider`, `base_url`, `api_key`,
`model`, `device`, `release` (none, llama-swap, ollama), `fallback_urls`,
`batch_size`, `concurrency`, `connect_timeout`, `timeout`, `prices`
(optional `input_per_mtok`, `output_per_mtok`, `per_unit` for cost
recording).

Profiles: `low-vram` (exclusive, small batches; needs llama-swap or Ollama),
`workstation` (shared), `cloud` (no local models, high concurrency).

Secrets come from the environment or a secrets file and are redacted in
`request.json` and in all server responses.

### Switching providers without a rebuild

Provider choice is runtime data, never part of a system build. A NixOS module
for wosarcher installs the package, runs the server, and points it at a
config directory; it does not contain provider URLs or model names.

**Client side (wosarcher).**

- Profiles are TOML files in `$XDG_CONFIG_HOME/wosarcher/profiles/`, a
  mutable directory, not the Nix store. Built-in profiles ship with the
  package; a user file with the same name overrides one.
- Select a profile per command (`wosarcher run --profile desktop "q"`), per shell
  (`WOSARCHER_PROFILE=desktop`), or as the default (`wosarcher profile use desktop`, which
  writes `$XDG_CONFIG_HOME/wosarcher/current`).
- Override a single field without a new profile:
  `wosarcher run --set score.provider=jev --set prefilter.base_url=http://desktop.lan:8002/v1 "q"`.
- The server reads the profile when each run starts (each run is a fresh
  `wosarcher run` subprocess), so changing a profile file or the default never needs
  a server restart. The frontend's New run screen lists profiles and accepts
  per-run overrides.
- `wosarcher profile list`, `wosarcher profile show <name>` (resolved, secrets redacted),
  and `wosarcher doctor --profile <name>` make switching safe.

**Model host side (each GPU machine).** One llama-swap service per machine,
in front of every model that machine may serve (rerankers, embedders, LLMs).
The NixOS module only starts llama-swap with a config file from a mutable
path and `--watch-config`; adding or changing a model is a YAML edit, not a
rebuild. Clients choose a model by the `model` field of the request, and
llama-swap starts it on demand, unloads it after its `ttl`, and keeps models
in the same group co-resident. This also replaces hand-written idle
watchdogs and health-wait scripts. Ollama, where used, already loads models
by name on demand. (Check flag and config names against the llama-swap
version in the pinned nixpkgs.)

The result: switching between a local and a remote reranker, or between two
models on the desktop, is a profile change on the client, and adding a model
to a machine is a config edit on that machine.

### Agent skill

The skill documents the CLI and the JSON schema of `context.json` and the
report. Agents usually want cited context: `wosarcher run "q" --until select
--json` returns passages with sources and scores. A full report is the
default `wosarcher run`.

### Evals

The eval harness measures prefilter and scorer choices over the same
inputs. It drives the public CLI only, so it measures what users run.

- `evals/variants.toml` names variants. Each forks from `prefilter` or
  `score` (any other stage is rejected) with a list of `--set` overrides.
  Model variants set `score.fallback=[]` so a broken service is a failed
  result, not a silent BM25 measurement.
- `python -m evals.replay (--runs ID... | --all) --variants NAME... --out
  DIR [--write] [--force] [--set KEY=VALUE]` runs `wosarcher fork <id>
  --from <stage> --until select --json` (through `write` with `--write`) in
  a subprocess, one at a time, and appends `{parent_run_id, variant,
  run_id, status, error, run_dir}` to `DIR/results.jsonl`. Search, fetch,
  and chunk are copied from the parent, so only ranking changes. A failed
  fork is recorded and the replay continues; finished pairs are skipped
  unless `--force`. `--all` takes every run with `version == 1` that
  finished `select`.
- `python -m evals.metrics --results DIR [--baseline NAME]` needs no
  model: selected passages, context characters and estimated tokens
  (characters / 4, rounded up), seconds of each stage the fork ran (from
  `stage.done` without `copied_from`), and the Jaccard overlap of selected
  chunk IDs between variants on the same parent run. It writes
  `DIR/metrics.json` and prints a Markdown table per variant with medians,
  p90 tokens and seconds, and the median overlap with the baseline (default:
  the first variant).
- `python -m evals.judge --results DIR [--profile NAME] [--set ...]` asks
  the profile's `llm` which selected passages are relevant to the query
  and records precision (relevant / selected) in `DIR/judgements.jsonl`;
  judged runs are skipped next time. Only the query goes through
  `evals/prompts/precision.md`; passages go in a separate user message. An
  unparsable answer records precision as missing.

The recorded-run fixture is `tests/fixtures/runs/20260101-000000-fixture/`,
a full `wosarcher run` of the `e2e` profile against recorded SearXNG,
Firecrawl, and LLM responses in `tests/fixtures/http/` (served by the respx
router in `tests/fixtures/recorded.py`; any other request fails naming its
URL). When a contract changes, `test_fixture_parses` names the artifact
that no longer parses; regenerate the fixture with `uv run python -m
tests.fixtures.make_recorded_run`. `tests/test_e2e_run.py` runs the same
pipeline with the real adapters and no network.

## Tech stack

Backend: Python 3.13, managed with uv. The work is I/O-bound HTTP
orchestration; every model is behind HTTP.

| Concern | Choice | Reason |
|---|---|---|
| Packaging | uv, `pyproject.toml`, `uv.lock` | fast, reproducible, works in the Nix dev shell |
| Contracts, config | pydantic v2; profiles read with stdlib `tomllib` and resolved by own code in `config.py` | one set of models for contracts, docs, config, and JSON Schema; precedence readable in one function |
| HTTP | httpx | async, explicit timeouts, easy to mock |
| CLI | typer, rich | readable commands and progress |
| Server | FastAPI, uvicorn, python-multipart | native WebSocket; serves the frontend build; multipart uploads |
| Markdown | markdown-it-py | real heading tree for chunking |
| Prompts | `.md` files with stdlib `string.Template` (`$query`) | no brace bugs, no template engine |
| Storage | JSONL and JSON files in `runs/` | no database; add a SQLite index only if listing gets slow |
| Tokens | characters divided by `llm.chars_per_token` (default 3.5), times `llm.token_margin` (default 1.1), rounded up, plus 16 per passage label | local models use different tokenizers; a profile that switches models sets the ratio |
| Tests | pytest, pytest-asyncio, respx, httpx2 | adapter tests without network; httpx2 is what Starlette's `TestClient` uses |
| Quality | ruff (lint and format), basedpyright (strict) | readability enforced by tools |

Frontend: Vite, React, TypeScript, react-markdown, Biome (format and lint);
pnpm. No server-side
rendering: FastAPI serves the static build from the same origin, which keeps
the cookie and `Origin` checks simple. The event and API types are generated
from the Pydantic models (JSON Schema, then json-schema-to-typescript); a
check fails when they drift.

### Frontend design

The visual design is the Claude Design handoff bundle in `design/`. It is
the source of truth for the frontend: the built UI matches it screen by
screen, in both themes and on phone and desktop.

- Primary file: `design/project/Sift Research.dc.html`. Its `scenario`
  values (live, loading, reconnecting, failure, cancelled, finished,
  versions, empty, new, login, login-wrong, login-limited) are the states the
  frontend must implement.
- Styling uses the bundle's Nocturne design system directly:
  `design/project/_ds/*/styles.css` is vendored into the frontend as the
  token sheet and component classes, with the prototype's light-theme
  overrides. Page-specific styles are CSS modules that use only Nocturne
  variables. No Tailwind or shadcn/ui: a second styling system would drift
  from the design.
- Icons: Phosphor (`@phosphor-icons/react`), as the design system requires.
- Fonts and icons are bundled with the build, not loaded from a CDN.
- The prototype's runtime (`support.js`, `x-dc`, `sc-if`, the scenario
  switcher) is not used; React components recreate the output.
- When the UI needs data the backend does not provide, the backend contract
  changes; the design is not reduced to fit.
- `docs/frontend-inventory.md` describes the prototype's screens,
  components, data, and interactions as a reading aid.

#### Frontend decisions

These override the prototype where they differ:

- **Name:** "wosarcher" everywhere the prototype says "Sift" (brand, token
  prefix `wosarcher_`, storage keys). No version string is hard-coded.
- **Citations:** `[n]` points to a passage; hover shows the passage text,
  source, and score.
- **Citation options:** two settings, `citation_marker` and
  `reference_style` (see Writing options).
- **Tones:** the 11 tones in Writing options. Default length 1200 words.
- **Scores:** shown as a 0 to 1 bar (`display`). `jev` scores are divided
  by 3; `bm25` scores are divided by the best score of the same query;
  other scorers (`rerank`) are shown as returned; all clamped to 0 to 1.
  The threshold line is `score.min_score / 3` for `jev`,
  `score.relative_threshold` for `bm25`, and `score.relative_threshold`
  times the query's best display score for other scorers. `passthrough`
  pairs have no score bar and no threshold line.
- **Device chip:** shows the stage's `device` label. VRAM figures are not
  shown; no source provides them.
- **Theme:** dark and light both kept; the first visit follows
  `prefers-color-scheme`, and the choice is remembered in the browser.
- **Sample data** in the prototype (fetch provider name, GPU model, socket
  URL, counts on the Report screen) is replaced by real data from the API
  and events. The socket URL is the page's own origin.

#### Frontend structure

The UI lives in `web/` (Vite, React, TypeScript, pnpm) and builds into
`web/dist`, which the server serves at `/`.

- **Routes** are URL fragments, parsed by `src/app/route.ts` with no router
  library: `#/new`, `#/live`, `#/live/<id>`, `#/runs/<id>` (Report),
  `#/history`, `#/settings`; anything else is `#/new`. Fragments never
  reach the server, so a reload keeps the screen.
- **Styles**: two vendored global sheets in `src/vendor/` (exempt from the
  token check): `nocturne.css`, the bundle's `styles.css` without its
  Google Fonts import, and `prototype.css`, the prototype's `<style>` block
  rescoped from `.sx` to `:root` (extra tokens, the light theme as
  `:root[data-theme="light"]`, keyframes, scrollbar, links). Every other
  style is a CSS module next to its component; values the prototype
  computes in JS (status, health, alert tints) are variants selected with
  `data-state` or `data-tone`. Inter (`@fontsource/inter`) and Phosphor
  (`@phosphor-icons/react`) are bundled.
- **Types**: `web/scripts/gen-types.mjs` compiles `wosarcher schema` into
  `src/api/generated.ts`; `src/api/types.ts` names what the UI uses and
  narrows the event union. `scripts/check --full` fails on drift.
- **Data layer**: `ApiClient` (`src/api/client.ts`) has one method per
  endpoint; `httpApi` throws `ApiError` (status, code, field errors) on
  non-2xx and locks the app on 401, and `login` returns `ok`, `wrong`, or
  `limited`. `RunEvents` (`src/api/events.ts`) owns one run's WebSocket:
  it reconnects 2 s after any close other than 1000 or 4404 (reading
  `GET /api/runs/{id}` first, then `since` = the last logged `seq`) and
  reports `connecting`, `connected`, `reconnecting` (attempt N),
  `replaying` (N events), or `closed`. `runReducer` (`src/run/reducer.ts`)
  folds events into one `RunView` (dedupe by `seq`; live-only events never
  move it), and `useRun` combines both. The app keeps the followed run's
  stream open on every screen for the Live run dot.
- **State**: React state in `App` behind three contexts (API, auth, UI:
  theme, toast, overlay stack for Escape, followed run, provider warning,
  pending History deletes). No store library.
- **Tests and preview**: screens are tested against `fakeApi` and
  `FakeWebSocket` (`src/test/`). In `pnpm --dir web dev`,
  `#/preview/<name>` renders the app on fixture data for side-by-side
  comparison with the prototype; production builds leave it out.

Nix: `flake.nix` dev shell with Python, uv, Node.js, and pnpm, loaded by
direnv. uv uses the Nix Python (`UV_PYTHON_DOWNLOADS=never`), because
downloaded Python builds do not run on NixOS without extra setup.

License: MIT.

## Build order

1. `models.py`, `ports.py`, `config.py`, `http.py`.
2. `lexical.py` (BM25) with unit tests; adapters: searxng, firecrawl, llm,
   rerank, jev, plus fakes; `wosarcher doctor`.
3. Stages: initial search and plan, search, fetch (dedupe, cap), load,
   chunk, score, select (thresholds, token budget), write (citations,
   writing options).
4. `RunStore`, `events.jsonl`, `wosarcher run`, `wosarcher fork`.
5. Recorded-run fixture and the eval replay harness.
6. Embeddings prefilter.
7. Server, frontend, skill.

## Maintainability rules

- One adapter per file, aim for under 200 lines.
- `scripts/check` (format, lint, architecture layering) passes before any
  work is done; `scripts/check_architecture.py` enforces the layering in
  Patterns used.
- Stages are pure; chunking and selection have unit tests.
- Pydantic models document every contract; hot per-chunk paths may use
  `model_construct`.
- Prompts and tones live in `prompts/`, not in Python strings.
- Plain `httpx`; no LangChain.
- End-to-end test with fakes and a recorded run.

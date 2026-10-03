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
(default 8000), they skip prefilter and score. Applies to web and files.

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
  next GPU stage uses the **same device label**. Stages on different devices
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
  different machine with a different model never reuses wrong vectors.
- **Health.** `wosarcher doctor` checks each endpoint: reachable, model name,
  latency of one small request, unload support (llama-swap answers
  `GET <root>/running`, Ollama `GET <root>/api/version`).

### Scoring

- A score is always for a pair: `Score(query_id, chunk_id, value, scorer)`.
- Web chunks are paired with every query that found their page.
- File chunks are paired with the main query and each sub-query, but only
  pairs that survive the prefilter (top-K per query) reach the scorer. A
  file chunk keeps its best pair; `best_query_id` is recorded so
  per-query quotas still work.
- Each scorer declares whether its scores are calibrated:
  - `jev`: calibrated 0 to 3; absolute threshold `score.min_score`
    (default 1.5).
  - `rerank`: not calibrated across queries; relative threshold
    `score.relative_threshold` (keep pairs scoring at least this fraction of
    the best pair for the same query, default 0.5).
  - `bm25`: local, no model, no API; values are relative to the best chunk
    for the query (best 1.0, others their fraction of it; when nothing
    matches, the first 25 chunks score 1.0 and the rest 0.0); relative
    threshold (default 0.5), up to 25 chunks per query.
  - `passthrough`: every chunk 1.0, so input order is kept.
  - All are capped by `score.top_k` per query.

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

**Fallback is per stage, not per call.** If the configured scorer fails, the
whole score stage reruns with the next scorer in `score.fallback` (default
`["bm25", "passthrough"]` after the configured one; only these two built-in
scorers are allowed, because the score block configures one remote
endpoint), so one run never mixes
score scales. The terminal fallback is `passthrough`: chunks in search-rank
order, then page order, capped by the token budget. A run never ends without
context.

### Select

Order of rules:

1. Scorer threshold.
2. Per-source cap (`select.max_chunks_per_source`).
3. Round-robin across queries, best score first, until the token budget is
   full.

The token budget is `llm.context_window` minus prompt and output tokens,
or `select.max_context_tokens` if lower. File and web shares are soft
(`select.file_share`, default 0.5): budget one side does not use flows to the
other, so `--sources files` uses the whole budget.

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
request, or the skill.

| Option | Default | Values |
|---|---|---|
| `tone` | `objective` | objective, formal, analytical, persuasive, informative, explanatory, descriptive, critical, comparative, speculative, reflective, or a custom name |
| `tone_instructions` | empty | free text added to the tone, for one-off styles |
| `words` | 1200 | target length |
| `language` | english | report language |
| `citation_marker` | numeric | numeric (`[1]`), superscript, author-year: how citations appear in the text |
| `reference_style` | APA | APA, MLA, Chicago, IEEE, ...: how the reference list is formatted |

Tones are data, not code: `prompts/tones.toml` maps each name to its
description (the gpt-researcher list is the starting set). Adding a tone is
one entry in that file.

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
- After writing, the runner checks that every `[n]` exists and reports
  unknown citations as warnings.
- The reference list groups the cited passages by source and is formatted by
  code in the chosen `reference_style`, with heading path or pdf-ingest page
  ID for files.

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
cli.py ── server.py (spawns `wosarcher run`, tails events.jsonl) ── skill (CLI + SKILL.md)
   │
runner.py  ── store.py (runs/<id>/) ── events.jsonl
   │
stages/  plan search fetch load chunk prefilter score select write   (pure)
   │ ports.py (Protocols)
adapters/  searxng firecrawl embeddings rerank jev llm  ── http.py
```

### Package layout

```
src/wosarcher/
  models.py      # Pydantic contracts (RunRequest, Query, Plan, Hit, Source, Page, Chunk, Attachment, Skipped, stage results, Score, Context, Report, WritingOptions, Message, Completion, EmbedderInfo, ProviderHealth, DoctorReport) and ID helpers
  ports.py       # Protocols: Searcher, Fetcher, Embedder, Scorer, LLM, Managed; the Adapters bundle
  config.py      # settings, profiles, precedence, secret redaction
  http.py        # ProviderClient: retry with backoff, fallback URLs, per-provider semaphore, SSE streams; unload; UsageLedger
  profiles/      # built-in low-vram.toml, workstation.toml, cloud.toml
  store.py       # RunStore: run directory, artifacts, caches (pages by URL, embeddings by SHA-256)
  runner.py      # runs stages in order, emits events, writes artifacts, handles cancel
  build.py       # composition root: config -> adapters (a dict, no registry)
  doctor.py      # provider health probes and exclusive-GPU warnings
  lexical.py     # BM25: tokenizer, scoring, relative threshold (pure functions)
  attachments.py # expands --attach paths and reads the files' bytes (the only attachment file I/O)
  stages/        # one file per stage
  adapters/      # one file per adapter, plus fakes.py
  prompts/       # __init__.py (load(name) -> string.Template from package data), jev.toml, plan.md, plan_data.md, write.md, tones.toml
  cli.py
  server.py
skill/SKILL.md
evals/
tests/
```

### Patterns used, and only these

- **Ports and adapters.** Stages depend on `Protocol`s, never on adapters.
- **Composition root.** `build(config)` creates adapters from a dict of
  constructors. No registry, no globals.
- **Pure stages.** `plan(query, snippets, outlines, llm) -> Plan`. A stage
  gets its inputs and ports, returns its output, and does not know about
  files or events. Tests need only fakes.
- **Repository.** `RunStore` owns paths and serialisation.
- **Append-only event log.** The runner assigns `seq`, writes the event to
  `events.jsonl`, then publishes it.

Cross-cutting concerns (retry, rate limits, costs) live in `http.py` as
plain functions used by adapters, not as generic decorators.

Prompt templates: Markdown files with `{placeholders}` filled only from
trusted values (query, options). Scraped text never goes through templates.

### Run directory

```
runs/<id>/
  request.json       # query, options, resolved config (secrets redacted)
  attachments/
  plan.json
  hits.jsonl
  pages.jsonl
  chunks.jsonl
  candidates.jsonl
  scores.jsonl
  context.json
  report.md
  events.jsonl
  costs.json
```

A stage is finished when its `stage.done` event is in `events.jsonl`; a
half-written artifact without that event is ignored.

### Commands

- `wosarcher run "q" [--attach ...] [--sources ...] [--until select] [--tone ...] [--words ...] [--json]`
- `wosarcher fork <id> --from <stage> [overrides]`: copies artifacts before
  `<stage>` into a new run and continues with the saved config plus the
  overrides. Used for resume, for changing writing options, and by the eval
  harness.
- `wosarcher doctor [--profile <name>] [--set k=v] [--json]`: one row per
  block (provider, base URL, device, status, model, latency, unload support);
  built-in scorers are shown without a request. Warns about blocks that
  cannot unload. Exit code 1 when any probe fails. The Firecrawl probe
  scrapes `https://example.com`, which spends one credit on the cloud API.
- `wosarcher runs`: lists runs.

### Events

- Run: `run.queued`, `run.started`, `run.done`, `run.failed` (stage and
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
- Write: `report.delta`.

Each event: `{seq, run_id, ts, type, stage?, data}`.

`report.delta` is live only and not written to the log. A reconnecting client
gets all logged events after its `seq`, then a `report.snapshot` built from
`report.md` so far.

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
tokens, Firecrawl credits. The runner writes `costs.json` and emits totals in
`stage.done`.

### Server

The server spawns `wosarcher run` as a subprocess per run and tails
`events.jsonl`, so the CLI, the server, and the skill share one code path.
Cancel sends a signal.

- `POST /runs` (multipart: request JSON plus attachments) returns `run_id`.
- `GET /runs`, `GET /runs/{id}`.
- `GET /runs/{id}/artifacts/{name}`: names from a fixed allowlist only.
- `POST /runs/{id}/cancel`.
- `POST /runs/{id}/fork` (stage plus overrides).
- `POST /runs/{id}/rerun`: a new run with the original request and a
  server-side copy of its attachments.
- `WS /runs/{id}/events?since=<seq>`.
- `GET /settings` and `PUT /settings`: global defaults, including writing
  options; each run can override them.
- `DELETE /runs/{id}`.
- `GET /profiles`: names, source, and which is active.
- `GET /providers/health`: the `wosarcher doctor` checks for the active
  profile.
- `GET /session`, `GET /tokens`, `POST /tokens` (the new token is returned
  once), `DELETE /tokens/{id}`.

Runs record lineage: `parent_run_id` and `version` (1 for a new run, parent
version plus one for a fork) and `fork_from` (the stage a fork started
from), which the Versions screen shows. Rerun is a new run (version 1, no
parent) with the same request and attachments; "Retry from Score" is a
fork from the score stage.

`server.max_concurrent_runs` (default 1) limits runs in progress; further
runs wait and emit `run.queued`.

### Authentication

One admin user, for local use: it keeps everyone but the owner out when the
server is reachable from other devices. No accounts, roles, or sign-up.

- **Bind.** The server binds to `127.0.0.1` by default. Binding to any other
  address (`--host 0.0.0.0` or a LAN IP) is refused unless a password is set.
- **Password.** `wosarcher auth set-password` prompts for a password and stores
  only its scrypt hash (Python standard library `hashlib.scrypt`) in the
  config directory, or in `WOSARCHER_AUTH__PASSWORD_HASH`. The plain password is
  never stored.
- **Browser session.** `POST /login` with the password sets a session cookie
  (a failed login answers with the attempts left; a rate-limited one with
  `retry_after` seconds):
  random token, signed with an HMAC secret, `HttpOnly`, `SameSite=Strict`,
  `Secure` when served over HTTPS, lifetime `auth.session_days` (30).
  `POST /logout` clears it. Changing the password rotates the secret, which
  ends every session.
- **WebSocket.** Browsers cannot set headers on a WebSocket, so the cookie
  is checked on the handshake, and the `Origin` header must match the
  server's own origin (prevents cross-site WebSocket hijacking).
- **CSRF.** `SameSite=Strict`, JSON-only request bodies (multipart only for
  `POST /runs`), and the same `Origin` check on every state-changing
  request.
- **Scripts and agents on other machines.** `Authorization: Bearer <token>`
  with a token from `wosarcher auth new-token`, stored hashed; tokens can be listed
  and revoked. The local CLI and the skill run `wosarcher` directly and need no
  auth.
- **Brute force.** Login attempts are limited per client IP (5 per minute,
  then exponential backoff), and failures are logged.
- **Transport.** On plain HTTP over Wi-Fi, the password and cookie can be
  sniffed. Use Tailscale (encrypted, and limits access to your devices) or a
  local reverse proxy with TLS (for example Caddy). The server must not be
  exposed to the internet.
- **Every route** except `GET /login`, `POST /login`, and static assets
  requires a valid session or token.

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

## Tech stack

Backend: Python 3.13, managed with uv. The work is I/O-bound HTTP
orchestration; every model is behind HTTP.

| Concern | Choice | Reason |
|---|---|---|
| Packaging | uv, `pyproject.toml`, `uv.lock` | fast, reproducible, works in the Nix dev shell |
| Contracts, config | pydantic v2; profiles read with stdlib `tomllib` and resolved by own code in `config.py` | one set of models for contracts, docs, config, and JSON Schema; precedence readable in one function |
| HTTP | httpx | async, explicit timeouts, easy to mock |
| CLI | typer, rich | readable commands and progress |
| Server | FastAPI, uvicorn | native WebSocket; serves the frontend build |
| Markdown | markdown-it-py | real heading tree for chunking |
| Prompts | `.md` files with stdlib `string.Template` (`$query`) | no brace bugs, no template engine |
| Storage | JSONL and JSON files in `runs/` | no database; add a SQLite index only if listing gets slow |
| Tokens | per-model character ratio with a safety margin; optional llama-server `/tokenize` | local models use different tokenizers |
| Tests | pytest, pytest-asyncio, respx | adapter tests without network |
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
- **Scores:** shown as a 0 to 1 bar. Jev scores are divided by 3; rerank
  scores are shown as returned; BM25 scores are relative to the best
  passage of the same query. The threshold line comes from the scorer's
  configured threshold, mapped the same way, not a fixed value.
- **Device chip:** shows the stage's `device` label. VRAM figures are not
  shown; no source provides them.
- **Theme:** dark and light both kept; the first visit follows
  `prefers-color-scheme`, and the choice is remembered in the browser.
- **Sample data** in the prototype (fetch provider name, GPU model, socket
  URL, counts on the Report screen) is replaced by real data from the API
  and events. The socket URL is the page's own origin.

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

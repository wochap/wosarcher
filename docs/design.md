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
- Multi-agent orchestration, source curation, report chat, and recursive
  child researchers.

## Pipeline

```
attachments ─► load ──────┬──────────────────────────────┐
                          │ outlines                     │
                          ▼                              ├─► pages ─► chunk ─► prefilter ─► score ─► gap ─► select ─► write
query ─► initial search ─► plan ─► search ─► fetch ──────┘                                              │
                                     ▲                                                                   │
                                     └──────────────── follow-up queries (research rounds) ──────────────┘
```

Load runs before plan so the planner sees attachment outlines. The initial
search runs only for a query of at most 200 characters (see Initial
search).

The user's query has two roles. The planner, the gap step, and the writer
read it whole, as the request. Search, fetch order, pairing, prefilter, and
scoring use `q0`, the planner's topic line: one short query that states
what the question is about. A one-line question and a 4,000-character
brief therefore search and rank the same way, and no stage after `search`
needs to know which one the user typed.

| Stage | Input | Output | Resource |
|---|---|---|---|
| plan | query, initial search snippets (short queries), attachment outlines | topic line `q0`, sub-queries | LLM |
| search | sub-queries, and `q0` when no initial search ran | hits (URL, title, snippet, query IDs) | network |
| fetch | hits | pages (markdown) | network |
| load | attachment bytes | pages, outlines | CPU |
| chunk | pages | chunks with heading path | CPU |
| prefilter | chunks, queries | top-K (query, chunk) pairs | GPU or API |
| score | pairs | scores | GPU or API |
| gap | best passages so far, queries | follow-up queries, note, stop flag | LLM |
| select | scores | context within a token budget | CPU |
| write | context, query, writing options | report with citations | LLM |

### Research rounds

With `research.rounds` above 1 (and web sources with at least one
sub-query), search, fetch, chunk, prefilter, score, and gap run as a loop,
one pass per round; select and write run once after it. Round 1 searches
the planner's sub-queries. After every round but the last, the gap stage
makes one LLM call: it reads the passages select picks from every round's
kept scores within the gap budget and the queries already run, and answers
JSON with up to `research.queries_per_round`
follow-up queries, a short note on what is missing, and an advisory `stop`
flag. Follow-ups get the next `qN` IDs, carry their `round`, and are
appended to `plan.json`; round k+1 searches them. With `rounds = 1` the gap
stage is skipped (`stage.done` with `skipped`) and nothing else changes.

The gap budget is `research.gap_context_tokens` (default 4000, a cheap call
on a small local model). With `auto` it is the room `llm.context_window`
leaves after `select.prompt_reserve_tokens`, the gap call's output limit
(768 tokens), and the estimated tokens of the main query and the existing
queries' text; a budget of 0 or less fails the gap step. A large-window
deployment sets `auto` in its profile, with `--gap-context-tokens`, or in
the API's `research.gap_context_tokens`.

The loop and its bookkeeping (`RoundState`: round number, pages fetched so
far, URLs seen, the scorer in use) live in the runner; the stages stay
pure. Each round:

- searches only its own queries (round 1 merges the initial hits);
- fetches only hits whose URL no earlier round fetched or queued (the rest
  count as known pages), within its round cap. `fetch.max_pages` counts
  across all rounds. With `left` pages left and `later` planned rounds
  after this one, the round cap is the larger of `left` minus a reserve of
  `research.queries_per_round` × `search.max_results` × `later` and the
  even share `ceil(left / (later + 1))`, never above `left`. The reserve is
  what follow-ups can use; the even share keeps round 1 from getting nothing
  when the reserve is larger than the room (deep: 20 of 60 pages, then 20
  of 40, then the last 20). The last round and single-round runs take
  `left`. The cap depends only on the settings and the pages fetched so
  far, so resume and fork compute it the same way;
- chunks its new pages, deduplicated against earlier chunks;
- prefilters and scores only pairs of its own queries with its new chunks,
  plus attached file chunks, so a page from an earlier round never pairs
  with a later query;
- starts with the scorer the previous round ended on, so a fallback stays
  in use;
- appends to the cumulative artifacts. After each round's score,
  `stages.score.keep_once` keeps every chunk for at most one query across
  rounds: the earliest round's pair wins.

Research stops at the first of these, checked in this order, and records
the reason: the gap call failed or its reply was unreadable (`gap step
failed`, a `gap failed: <error>` warning, the run continues); the pages
fetched reached `fetch.max_pages` (`page limit reached`); a round after the
first fetched no new page (`no new sources`); the last round ran (`max
rounds`); the gap step set `stop` or no follow-up survived its checks
(`model judged coverage sufficient`). The page limit and no-new-sources
checks run before the gap call, so no call is wasted. A gap timeout counts
as a failed gap step; every other stage timeout applies per round and fails
the run. Usage of a stage that runs in several rounds is summed in
`costs.json`.

Resume and fork: the loop stages of a multi-round run count as finished
only after `research.done`. A run resumed before that resets `plan.json` to
its round-1 queries, empties the loop's artifacts, and restarts the loop at
round 1 without calling the planner again; the page and embedding caches
make the repeat cheap. A fork from a loop stage copies only the `load` and
`plan` artifacts (the plan filtered to round 1) and reruns the loop; a fork
from `select` or `write` copies every round and `research.json`.

On `gpu_policy = exclusive`, release decisions use the real next stage,
cyclic inside the loop (score, gap, search, …, prefilter), so a low-VRAM
machine swaps models up to three times per round. Fewer rounds or a remote
scorer keeps that down.

### Initial search

Kept from gpt-researcher: one SearXNG call with the main query before
planning, so the planner sees real result titles and snippets, not only the
query. Snippets are short and come from SearXNG, not from scraped pages, so
fetched content never reaches the planner (the gap step reads passages; see
Prompt injection).

It runs only when web sources are on and the query is at most 200
characters after trimming. Its hits carry `q0`, and the search stage does
not search `q0` again in round 1. A longer query (a brief) is not searched
before planning: search engines reject it or match a few of its words.
`initial.jsonl` stays empty, the planner gets no snippets, and the search
stage searches `q0` (the topic line) with the sub-queries. The rule depends
only on the query's length, so the plan and search steps, a resume, and a
fork all decide the same way.

`MAX_SEARCH_CHARS = 200` in `stages/search.py` is the one limit: the
initial search rule, the fallback topic, the gap step's follow-up length,
and the search stage, which cuts every query text it sends to the searcher
at the last whitespace within 200 characters (the plan keeps the full
text). It is a constant, not a setting: it reflects what search engines
accept.

### Topic line

The planner answers `{"topic": "...", "queries": [...]}` in one call: a
topic line of at most 200 characters, which becomes the text of `q0`, and
one sub-query per distinct topic of the question, up to
`plan.max_sub_queries` (fewer for a narrow question). A sub-query that
repeats the topic or the user's query (ignoring case) is dropped. A bare
list still yields the sub-queries; an empty or longer topic counts as
missing. When the planner does not run (sources `files`,
`plan.max_sub_queries = 0`), gives no usable topic, or its answer cannot be
read, `q0` is the fallback topic: the user's query, cut like a search
query, or whole with sources `files` (nothing is searched; `q0` only
scores the files). A missing or unreadable topic adds a warning.

### Dedupe

- URLs are normalised (scheme, host case, trailing slash, tracking
  parameters, fragments) and fetched once per run, even when several
  sub-queries find them. A hit records every query ID that found it.
- Chunks with the same normalised-text hash are kept once.

### Fetch cap and order

Fetch succeeds on at most `fetch.max_pages` pages (default 40, the most
that default settings find: (1 + 3 sub-queries) × 10 results); a
multi-round run splits it with the round cap (see Research rounds). Unique hits
are queued round-robin over query IDs in query order (`q0` first), each
query's hits by rank; a hit found by several queries is queued once, at its
earliest turn. Up to `fetch.concurrency` workers take hits in queue order,
and a worker takes the next one only while pages fetched plus fetches in
flight are below the cap, so a failed or empty fetch frees its slot for the
next hit. Hits never fetched are not failures: fetch's `stage.done` reports
them as `unfetched`.

### Small-input passthrough

When all pages for a query total less than `select.passthrough_chars`
(default 8000), they skip prefilter and score, whatever scorer the run
uses. Their pairs are ordered by search rank, page order, and chunk
position, and the first `score.top_k` are kept with `passthrough` scores;
the rest are dropped with `query_cap`, so a small query cannot flood the
context with unscored chunks. The `passthrough` fallback scorer is not
capped. Applies to web and files.

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
  prefilter and score). The read `timeout` defaults to 60 s, and to 300 s in
  the `llm` block: a small local model on a consumer GPU can take minutes to
  process a long prompt before its first token. The local profiles set
  `llm.timeout = 600` so a model load behind llama-swap also fits.
  Larger batches amortise network latency.
- **Retries.** HTTP 429, 502, 503, 504, and 529 are retried on the same URL
  with exponential backoff (0.5 s doubling, each wait at most 8 s) or the
  `Retry-After` header, while the total wait on that URL stays within the
  block's `retry_budget` (default 60 s) and at most 10 retries; a wait that
  would exceed the budget fails the call at once. `retry_budget = 0`
  disables retries. Connection failures and connect timeouts go to the next
  fallback URL at once; read timeouts are not retried.
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
  `GET <root>/running`, Ollama `GET <root>/api/version`). Checks run only on
  request (the CLI, a Check click in Settings, or `run.preflight`), because
  a probe to a self-hosted server loads its model. A block is local when its
  `release` is not `none` or it sets a `device`; local blocks are probed one
  at a time in block order, beside the concurrent cloud probes, and under
  `gpu_policy = "exclusive"` a local model that can unload is released
  before the next local probe.

### Scoring

- A score is always for a pair: `Score(query_id, chunk_id, value, scorer)`.
- Web chunks are paired with every query that found their page.
- File chunks are paired with the main query and each sub-query. Only
  pairs that survive the prefilter (`prefilter.top_k` per query, default
  50, by embedding similarity or BM25, or all with `none`) reach the
  scorer. If the embedder fails, or returns a vector of another dimension,
  the prefilter uses BM25 for the whole stage and records a warning.
  Embeddings are cached by the SHA-256 of the text; the cache refuses a
  vector whose dimension differs from its identity.
- Each scorer declares whether its scores are calibrated:
  - `jev`: calibrated 0 to 3; absolute threshold `score.min_score`
    (default 1.5).
  - `rerank`: not calibrated across queries; relative threshold
    `score.relative_threshold` (keep pairs scoring at least this fraction of
    the best pair for the same query, default 0.5), applied to the mapped
    score. Rerankers return either probabilities (0 to 1) or raw logits;
    `score.rerank_scale` (`auto`, `probability`, `logit`) names the scale,
    and `auto` picks `logit` when any raw score of the stage is outside
    [0, 1], so one stage never mixes scales. On the logit scale the mapped
    score is the sigmoid `1 / (1 + e^-x)`; on the probability scale it is
    the raw score. Raw scores stay in `scores.jsonl`. When no mapped score
    of a query is positive, only its best pair is kept.
  - `bm25`: local, no model, no API; raw BM25 values, kept by the lexical
    ranking rule: relative threshold (default 0.5), zero scores dropped, up
    to 25 chunks per query, and the first chunks in page order when nothing
    matches.
  - `passthrough`: values `len - i` in search-rank, page, position order,
    so that order is kept; every pair is kept.
- After thresholds, every scorer except `passthrough` is capped at
  `score.top_k` kept pairs per query (default 10), best first.
- Then every chunk (web or file) keeps only its best pair across queries
  (highest display score, ties to the earlier query); that query is its
  best query ID, so per-query quotas still work and no chunk is selected
  twice. A pair the cap removed takes no part, so a chunk cut by the cap of
  its best query stays kept through another query that kept it; a query
  can end with fewer than `score.top_k` kept pairs.
- Every pair that is not kept records the first rule that dropped it in
  `Score.dropped`: `threshold` (the scorer's keep rule, including the BM25
  rule), `query_cap`, or `other_query`. `kept` is unchanged; `dropped` only
  explains it.

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
stage: the configured scorer, then exactly the entries of `score.fallback`
(only `bm25` and `passthrough` are allowed, because the score block
configures one remote endpoint). Nothing is appended. If any call of a
scorer fails, the whole score stage reruns with the next entry, so one run
never mixes score scales. The default `["bm25", "passthrough"]` ends in
`passthrough`, which never fails: chunks in search-rank order, then page
order, capped by the token budget, so a default run never ends without
context. When every entry fails (for example `score.fallback = []` and the
scorer is down), the score stage fails and its error names each scorer
with its error. The runner reports what the stages did: one `stage.failed`
per scorer that failed (with the scorer that ran next) and
`stage.done.provider` naming the scorer or prefilter method that actually
ran. The prefilter falls back from embeddings to BM25 the same way, inside
its stage.

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
`min(select.max_context_tokens, llm.context_window - select.prompt_reserve_tokens - query - output)`,
where `output = min(max(1024, 2 * words), llm.max_output_tokens)` is also
the write call's output limit, sent as `llm.max_tokens_field`, and `query`
is the user's query estimated like a passage (`llm.chars_per_token`,
`llm.token_margin`): the writer's prompt holds the full query on top of the
fixed text `prompt_reserve_tokens` (2000) covers, and a 4,000-character
brief is about 1,260 tokens. `select.max_context_tokens` defaults to
`auto`, which drops the cap: the budget is all the room the window leaves.
Passages are already bounded by queries × `score.top_k`, so a fixed cap
only dropped scored passages as over budget. A profile or run can still set
a number. A budget of zero or less is an error naming `llm.context_window`
and the prompt, query, and output tokens it subtracted.

File and web shares are soft and run in two phases: when both sides have
passages, files first get `floor(select.file_share * budget)` (default
0.5) and the web the rest; then the passages left on both sides share
whatever budget is unused, by the same round-robin. `--sources files` uses
the whole budget. Passages are numbered `1..N` in the order taken.

`select` returns a `Selection`: the `Context` the writer reads, and one
`SelectSkip` (chunk ID, best query ID, reason) for every kept passage it
did not take. The reason is `source_cap` for passages the per-source cap
removed, and `budget` for passages still left after the last round-robin
pass; a `budget` skip also carries `tokens_needed` (the passage's cost) and
`tokens_left` (the budget left at the end). The runner writes the context
to `context.json` and the skips to `select.jsonl`.

### Attachments

- `wosarcher run "q" --attach notes.md --attach ./docs/` (files, directories, globs).
  `attachments.py` expands the paths (directories recursively in sorted
  order, hidden parts skipped) and reads the bytes; a path that matches
  nothing fails the run before any stage. The load stage only sees bytes,
  so the server can pass uploads without touching disk.
- Formats: `.md` and `.txt`; other files in a directory are skipped with a
  warning. UTF-8 with replacement; size limit `attach.max_bytes`. Identical
  content is loaded once. Neither `fetch.max_chars` nor `fetch.max_pages` applies: both are for web pages
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
| `words` | 1200 | target length; a depth preset sets its own default (Quick 600, Deep 2000, Exhaustive 3000; Standard keeps this one) |
| `language` | english | report language |
| `citation_marker` | numeric | numeric (`[1]`), superscript, author-year: how citations appear in the text |
| `reference_style` | APA | APA, MLA, Chicago, IEEE (case-insensitive): how the reference list is formatted |

Tones are data, not code: `prompts/tones.toml` maps each name to its
description (the gpt-researcher list is the starting set). A custom tone is
one more entry in that file. The write stage checks `tone` against that file
and `reference_style` against the four known styles before calling the LLM;
an unknown name fails with the list of known names.

The report's output limit is `max(1024, 2 × words)`, capped at
`llm.max_output_tokens` (default 8192), so every preset's target fits the
default cap. The same number is the output allowance of the context budget
(see Select).

A report cut at the output limit (finish reason `length`) is continued, up
to `llm.max_continuations` times (default 2; 0 turns it off). A
continuation sends the first two messages, then the text so far as an
`assistant` message and the instruction in `prompts/write_continue.md` as a
`user` message. Its output limit is the report's, lowered to the room left
in `llm.context_window` by the estimated input (`llm.chars_per_token`,
`llm.token_margin`); under 256 tokens of room, the writer stops. A
continuation that starts by repeating at least 20 characters of the text's
end has the repeat removed before it streams. A failed continuation keeps
the text and warns `continuation failed: <error>`. `report.json` records
`continuations` and `truncated`; a truncated report warns `report
truncated at the output limit of <N> tokens`, plus ` after <k>
continuations` when k > 0. Each continuation re-sends the passages, so
hosted models bill their input again. The Report screen shows "Continued
N×", or the cut note and an end marker before References.

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

- Fetched content never reaches the planner. Its prompt template takes
  only the query and `plan.max_sub_queries`; initial hit titles and
  snippets (short queries only) and attachment outlines go in a separate,
  delimited data message. The topic line it returns becomes a search query,
  so it is held to the same 200-character limit as follow-ups.
- The gap step does read scraped passages, and its output becomes search
  queries. Only the main query, the follow-up limit, and the date go
  through `prompts/gap.md`; the existing queries and the passages go in one
  user message after the `prompts/gap_data.md` preamble, in a delimited
  `<data>` block whose closing text is escaped. Follow-ups are validated:
  empty ones, ones over 200 characters, ones with a URL (`https?://` or
  `www.`), and duplicates of any query (ignoring case and surrounding
  whitespace) are dropped, and at most `research.queries_per_round` are
  kept. They only feed SearXNG queries, never a tool call or a fetch the
  user did not cause; the worst case is an off-topic search.
- The writer sends `system` then one `user` message: an instruction to treat
  the following block as data, not instructions, the delimited
  `<passages>` block, and after it the writing task. Text that would close
  the block is escaped. One user message keeps chat templates that require
  alternating roles working.
- Scraped text is never passed through `str.format` or a template engine;
  it is inserted as a whole block.

## Adapters

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

The LLM adapter sends the output limit plus `llm.reasoning_tokens` under
`llm.max_tokens_field` (`max_completion_tokens` by default, `max_tokens` for
servers that need it; never both). An answer with empty content and finish
reason `length` fails with an error naming `llm.reasoning_tokens`. Streaming
fails with a provider error on an event with an `error` member, and reports
the last `finish_reason` to the caller's `on_finish` callback. When it is
`length`, the writer continues the report (see Writing options).

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
  runner/        # __init__.py: Runner (stage loop, research rounds, timeouts, costs, cancel); steps.py: one function per stage, RoundState;
                 # events.py: EventLog, snapshot_event; devices.py: needs_release; caches.py: CachedFetcher, EmbeddingMapping
  build.py       # composition root: config -> adapters (a dict, no registry)
  doctor.py      # provider health probes and exclusive-GPU warnings
  lexical.py     # BM25: tokenizer, scoring, relative threshold (pure functions)
  attachments.py # expands --attach paths and reads the files' bytes (the only attachment file I/O)
  stages/        # one file per stage
  adapters/      # one file per adapter, plus fakes.py
  prompts/       # __init__.py (load(name) -> string.Template from package data), jev.toml, plan.md, plan_data.md, gap.md, gap_data.md, write.md, passages.md, write_task.md, tones.toml (tones())
  cli/           # __init__.py: typer app (profile, doctor, schema); run.py: run, fork, runs; logs.py: logs, event lines, stderr listener;
                 # serve.py: serve; auth.py: auth; progress.py: rich Live view
  __main__.py    # python -m wosarcher
  server/        # __init__.py: create_app; manager.py: RunManager (queue, subprocesses, cancel); staging.py: runs/.queue/ and argv;
                 # tail.py: RunTail; routes.py: /api/runs; meta.py: settings, profiles, health routes;
                 # health.py: HealthCache (stored provider checks); stream.py: event socket;
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
- **Append-only event log.** `RunStore.append_event` assigns `seq` (the
  last complete line's `seq` plus 1, read from the end of `events.jsonl` on
  every append, so another store or process appending later never repeats
  a `seq`) and writes the event to `events.jsonl`, on a new line when the
  file ends with a partial one; the runner then publishes it. Readers skip
  lines that do not parse (a partial line, a type from another version).

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
  plan.json          # plan, then each round's follow-up queries
  initial.jsonl      # plan: hits of the initial search for the main query
  hits.jsonl         # search: all hits of every round, initial ones merged in
  pages.jsonl        # fetch: web pages of every round
  chunks.jsonl
  candidates.jsonl
  scores.jsonl
  research.json      # gap: multi-round runs only; ResearchRecord
  context.json
  select.jsonl       # select: kept passages not selected, with the reason
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

Queries, hits, pages, and scores carry the `round` they first appeared in
(1 for single-round runs and files). `research.json` holds `planned`,
`ran`, `reason`, `note` (the end note: the gap note for `model judged
coverage sufficient`, a fixed sentence for `no new sources`, else empty),
and one entry per round with `round`, `query_ids`, `new_pages`,
`known_pages`, `kept`, and the gap `note` written after it.

A stage is finished when its `stage.done` event is in `events.jsonl`; a
half-written artifact without that event is ignored. Artifacts are written
to `<name>.tmp` and renamed. A stage skipped by `--sources` writes empty
artifacts and a `stage.done` with `skipped`. Each stage has a timeout in
`run.stage_timeouts`.

### Commands

- `wosarcher run "q" [--attach ...] [--sources ...] [--until select] [--depth NAME] [--tone ...] [--words ...] [--sub-queries N] [--results-per-query N] [--max-pages N] [--passages-per-query N] [--context-tokens N|auto] [--gap-context-tokens N|auto] [--rounds N] [--run-id ID] [--json]`:
  writing flags act as `--set write.<field>=...` and research flags as
  `--set` on `plan.max_sub_queries`, `search.max_results`,
  `fetch.max_pages`, `score.top_k`, `select.max_context_tokens`,
  `research.gap_context_tokens`, and `research.rounds`, after the `--set`
  values. The two token flags take a positive integer or `auto`. `--until` on a loop stage
  stops after that stage in round 1. The progress view shows a `gap` row
  only for multi-round runs, "round k/N" on running loop rows, and one
  final line "research: <ran> of <planned> rounds · <reason>". `--depth` applies a depth preset below all of them
  and is recorded in `request.json` (`request.depth`); forks keep it.
  `--run-id` lets a caller (the server) choose the ID; an existing directory
  exits 2. `--json` prints one `RunOutput` document (status, error, run
  directory, context when select finished, report when write finished). On a
  terminal, progress goes to standard error; piped output is the report
  Markdown. Exit status: 0 done, 1 failed, 130 cancelled (SIGTERM, SIGINT),
  2 invalid arguments or configuration.
- `wosarcher fork <id> --from <stage> [overrides] [--gap-context-tokens N|auto] [--profile NAME] [--until ...] [--run-id ID] [--json]`:
  copies `attachments/` and the artifacts before `<stage>` into a new run
  (version: the highest version in the parent's lineage plus one), logs a
  copied `stage.done` per earlier stage whose `copied_from` names the run
  that executed the stage (the parent's own `copied_from` when it copied the
  stage too, else the parent), and continues with the saved config (secrets taken from the current
  environment) plus the overrides. With `--profile`, settings come from that
  profile plus the parent's and the new overrides. Used for resume, for
  changing writing options, and by the eval harness.
- `wosarcher depth list` (each preset with its description) and `wosarcher
  depth show NAME` (the keys it sets, or "sets nothing; uses the
  defaults"); an unknown name exits 2 with the known names.
- `wosarcher doctor [--profile <name>] [--set k=v] [--block <name>...] [--json]`:
  `--block` (repeatable) limits the check, its rows, and its warnings to the
  named blocks; an unknown name fails before any request. One row per
  block (provider, base URL, device, status, model, latency, unload support;
  `--json` adds each block's configured `release` and the profile's
  `gpu_policy`);
  built-in scorers are shown without a request. Warns about blocks that
  cannot unload. After a successful LLM probe it reads the server's `n_ctx`
  from `GET <root>/props` (or `<root>/upstream/<model>/props` behind
  llama-swap), shows it as a note, and warns when it is below
  `llm.context_window`. The rerank row's note shows the probe's raw score
  and its scale (`probe score -3.25 (logit scale)`). Warnings and notes do
  not change the exit code. Exit code 1 when any probe fails. The Firecrawl probe
  scrapes `https://example.com`, which spends one credit on the cloud API.
- `wosarcher runs [--limit N] [--json]`: lists runs newest first as
  `RunSummary` rows, with status from the last `run.*` event: `done`,
  `failed`, `cancelled`, or `interrupted` (started without an end), plus
  `until`, `fork_from`, the resolved writing options, `duration_s`
  (`run.started` to the terminal event), and `cost` (from `costs.json`).
- `wosarcher logs <id> [--follow] [--profile NAME] [--set k=v]`: prints the
  run's logged events, one line each: `<HH:MM:SS> <stage or -> <type>
  <summary>` (local time; the summary on one line, at most 160 characters).
  Unreadable lines are skipped. `--follow` polls every 0.5 s and exits 0
  after a terminal event. An unknown run exits 2.
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
- Fetch: `page.fetched`, `page.failed` (reason: the first line of the
  error, at most 200 characters; the full text goes to standard error).
- Score: `passages.scored`, one per query: counts, the scorer that actually
  ran, and the kept passages (text, heading path, source, display score).
  The full list, including pairs that were not kept and why, is the
  `scores.jsonl` artifact.
- Research rounds (multi-round runs only): `round.done` (stage `score`),
  `gap.ready` (stage `gap`), `research.done` (stage `gap`).
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
| `stage.started` | `device`, `provider`, `round` |
| `stage.progress` | `done`, `total`, `failed`, `round` (at most every 250 ms, plus a final one) |
| `stage.done` | `count`, `seconds`, `usage` (`UsageTotals` with `cost`, that round's), `provider`, `skipped`, `copied_from`, `warnings`, `passthrough`, `unfetched`, `round` |
| `stage.failed` | `error`, `next` (empty when none) |
| `resource.waiting`, `resource.released` | `device`, `released_stage` |
| `plan.ready` | `queries` |
| `hit.found` | `url`, `title`, `query_ids` |
| `page.fetched` | `url`, `source_id`, `title`, `chars`, `cached`, `round` |
| `page.failed` | `url`, `reason` |
| `passages.scored` | `query_id`, `scorer`, `scored`, `kept`, `threshold_display`, `passages` (`KeptPassage`) |
| `round.done` | `round`, `query_ids`, `new_pages`, `known_pages`, `kept` |
| `gap.ready` | `round` (the round it followed), `queries` (follow-ups), `note`, `stop` |
| `research.done` | `planned`, `ran`, `reason`, `note` |
| `report.delta`, `report.snapshot` | `text` |

`round` is the research round (1 for single-round runs and for stages
outside the loop).

`provider` is `<provider>:<model>`, or `<provider>` when the block has no
model (`built-in` for stages without a block). On `stage.started` it is
the configured block; on `stage.done` it names what actually ran, in the
same form. Prefilter reports `embeddings:<model>` when embeddings ran as
configured, and `bm25` or `none` otherwise. `passthrough` lists, in plan
order, the sub-queries whose pairs skipped ranking (small-input
passthrough); only prefilter sets it.

`seq` is assigned by the store's append, so the log has no gaps.
`run.queued`, `report.delta`, and `report.snapshot` are live only and never
written to `events.jsonl`; on the socket they carry the last logged `seq`
sent to that client (0 when none). So do the terminal events of a run that
has no run directory (cancelled while queued, or its process exited
first): they have `seq` 0 on the server. Clients apply `run.done`,
`run.failed`, and `run.cancelled` whatever their `seq`, without moving
their last `seq`; every other event is deduplicated by `seq`. The report text is appended to
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
  `release()` is called in `exclusive` mode, `costs.json` is written with
  the usage so far, and `run.cancelled` is emitted.
- Diagnostics: when no progress view is shown (standard error is not a
  terminal, or `--json`), the run process writes one `INFO` line per
  `run.*`, `stage.started`, `stage.done`, `stage.failed`, and
  `resource.*` event (the `wosarcher logs` format; `WARNING` for
  `run.failed` and `stage.failed`), a `WARNING` line per `stage.done`
  warning, and each page failure's full text, to standard error. With the
  progress view, nothing else is written under it.

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
  `attachments` files, reduced to their base names; duplicates are 422,
  and so are sources `files` with no attachment, as `invalid_attachment`
  before anything is staged) returns 201 with `run_id` and `queued` or
  `running`. `RunCreate` has `query`, optional `sources`, `until`,
  `profile`, `depth` (a preset name or `custom`; unknown is 422 naming
  `depth`), `research` (`sub_queries`, `results_per_query`, `max_pages`,
  `passages_per_query`, `context_tokens`, `gap_context_tokens`, `rounds`
  at most 8; the two token values may also be `auto`), `writing`,
  and `set`. Request
  precedence, each later layer winning: defaults, profile, environment,
  global settings, the depth preset, the request's `sources`, `research`,
  and `writing`, then its `set`. The server builds the writing flags from
  the global writing, then the preset's `write.words`, then the request's
  `writing`; passes `--depth`; and emits the research values as `--set`
  after the writing flags and before the request's `set`.
- `GET /api/runs`, `GET /api/runs/{id}`: `RunSummary` (status `queued`,
  `running`, `done`, `failed`, `cancelled`, `interrupted`; lineage;
  `until`; `depth`, null for older runs; resolved writing options; `duration_s`; `cost`;
  `queue_position`; `error`, the `run.failed` text when failed; `end_stage`,
  the stage named by a final `run.failed` or `run.cancelled`;
  `rounds_planned`, the resolved `research.rounds`; `rounds_ran`, from
  `research.done`, 1 for a single-round run past the loop, else null;
  `stop_reason`, null for single-round runs), and for one
  run `RunDetail` (plus the redacted `request.json`, `costs`, `last_seq`).
  Runs that ended without a run directory are listed too (see below).
- `GET /api/runs/{id}/artifacts/{name}`: only `request.json`,
  `files.jsonl`, `plan.json`, `initial.jsonl`, `hits.jsonl`, `pages.jsonl`,
  `chunks.jsonl`, `candidates.jsonl`, `scores.jsonl`, `research.json`,
  `context.json`, `select.jsonl`, `report.md`, `report.json`,
  `events.jsonl`, `costs.json` (JSON as
  `application/json`, JSONL as `application/x-ndjson`, Markdown as
  `text/markdown`, UTF-8); anything else is 404.
- `GET /api/runs/{id}/sources/{source_id}`: `SourceView`, one source's
  stored chunks in page order, each with a state per sub-query
  (`not_in_results`, `prefiltered`, `pending`, `below_threshold`,
  `query_cap`, `other_query`, `kept`) and a final fate (`cited`,
  `source_cap`, `budget`, `kept`, `query_cap`, `below_threshold`,
  `prefiltered`, `pending`) with its rank, the sub-query's kept count, and
  budget figures. `removed_before` counts near-duplicates from gaps in
  `position`. It is computed by `server/sources.py` from whichever
  artifacts exist (`request.json`, `plan.json`, `files.jsonl`,
  `pages.jsonl`, `chunks.jsonl`, `candidates.jsonl`, `scores.jsonl`,
  `select.jsonl`, `context.json`); the display threshold comes from the
  score stage's `threshold_display`. 404 `run_not_found` or
  `source_not_found`.
- `POST /api/runs/{id}/cancel`:

  | Run state | Status | Body |
  |---|---|---|
  | running | 202 | `{"run_id", "result": "signalled"}`; SIGKILL after 10 s, then the server logs `run.cancelled` |
  | queued | 200 | `{"run_id", "result": "dequeued"}`; connected clients get `run.cancelled` |
  | done, failed, cancelled, interrupted | 409 | `RunNotActive`: `{"error": "run_not_active", "detail", "run_id", "status"}` |
  | unknown | 404 | `run_not_found` |
- `POST /api/runs/{id}/fork` (`from`, optional `writing`, `set`,
  `profile`): `wosarcher fork` through the queue. A fork keeps the parent's
  configuration: only the request's writing fields and `set` are passed,
  not the global settings. 409 for a queued or running parent or an
  unfinished earlier stage; 422 for an unknown stage.
- `POST /api/runs/{id}/rerun`: a new run (version 1, no parent) with the
  original query, sources, `until`, profile, depth, and saved overrides, and a
  copy of its `attachments/`; global settings are not applied. 404 for an
  unknown run, 409 for a queued one, 422 `invalid_attachment` for sources
  `files` without attachments.
- `WS /api/runs/{id}/events?since=<seq>`: replays logged events after
  `seq`, sends a `report.snapshot` when the report is not empty and
  `run.queued` while queued, then live events and `report.delta` until a
  terminal event, and closes with 1000. Unknown runs close with 4404; a
  client more than 1000 events behind is closed with 4408 and reconnects
  with `since`. Runs not owned by this server (finished, interrupted, or
  started by the CLI) are replayed and closed. The run is looked up after
  the socket is accepted, so a run that ends during the handshake is
  treated as ended; a run that ended without a run directory gets its
  terminal event (`seq` 0) and 1000.
- `GET /api/settings` and `PUT /api/settings`: global defaults
  (`ServerSettings`: all writing options and `sources`), stored in
  `<config dir>/server-settings.json`. They apply only to runs started by
  the server, as `--set write.*` values after the profile and before the
  request's `writing` and `set` (request wins). CLI runs use the profile.
- `DELETE /api/runs/{id}`: 204 for a finished run, a queued one, or one
  that ended without a run directory (forgotten), 409 `run_active` for a
  running one.
- `GET /api/profiles`: `name`, `source` (`builtin` or `user`), `active`,
  `description` (empty when the profile sets none), and the resolved
  `context_window`, `prompt_reserve_tokens`, and `max_output_tokens` (all
  null when the profile does not resolve), so the New
  run form can show the effective context budget.
- `GET /api/depths`: the presets in order (`quick`, `standard`, `deep`,
  `exhaustive`), each `DepthInfo` with `name`, `description`, and `values`
  (`sub_queries`, `results_per_query`, `max_pages`, `passages_per_query`,
  `context_tokens`, `gap_context_tokens`, `rounds`, `queries_per_round`,
  the built-in default where the preset sets none; the two token values
  are a number or `auto`, and `words`, null when the preset leaves it to
  the global setting).
- `GET /api/providers/health[?profile=P]`: sends no probe. It resolves the
  profile in the server process (400 `invalid_profile` on a configuration
  error) and lists one check per block, merged with the last stored check
  of that profile and block: built in is `skipped`, a block never checked
  is `unchecked`, and a stored check whose configured provider, base URL,
  or model no longer matches is ignored. Each check carries its
  `checked_at`, the report the profile's `gpu_policy`, the last check's
  warnings, and each check its `release`. Stored checks live in memory on
  `ServerState.health` (`server/health.py`) until the server restarts.
- `POST /api/providers/health/check[?profile=P]` with optional
  `{"blocks": [...]}` (`HealthCheckRequest`; none means every block): 400
  `invalid_block` for an unknown name, else runs `wosarcher doctor --json
  [--block ...]` under a lock (one check at a time; 60 s timeout; 502 when
  it times out or prints no report, stored checks unchanged), stores each
  row with the time of the check, and returns the merged report. Mapping:
  failed is `down` (error as detail), a model that cannot unload or a probe
  over 1000 ms is `degraded`, else `ok`.
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
`ProviderCheck`, `HealthReport`, `HealthCheckRequest`, `ApiError`, `RunNotActive`, `LoginRequest`,
`SessionInfo`, `TokenInfo`, `TokenCreate`, `TokenCreated`, `LoginError`) are models in `models.py` and
part of `wosarcher schema`.

Runs record lineage: `parent_run_id` and `version` (1 for a new run; for a
fork, the highest version among the runs of its lineage, the root and every
run whose parent chain reaches it, plus one, so versions are unique in a
lineage) and `fork_from` (the stage a fork started
from), which the Versions screen shows. Rerun is a new run (version 1, no
parent) with the same request and attachments; "Retry from Score" is a
fork from the score stage.

`server.max_concurrent_runs` (default 1) limits run processes; further runs
wait in FIFO order and get `run.queued` with their position (1 is next).
A queued run is staged in `runs/.queue/<id>/` (request and attachments)
until its process starts, and staged runs are queued again in creation
order when the server starts. When a process exits without a terminal
event, the server appends `run.failed` with the exit code and the last 20
lines of standard error. Whatever fails while the server watches or
finishes a run (an unreadable event line, a standard-error line of any
length, a failed write), the error is logged and the run is still
finalised: the tail closed, staging removed, the slot freed, and the next
run started. A queued run that is cancelled, or a process that exits before
creating its run directory, is remembered in memory (at most 100) with its
terminal event and staged request: `GET` and the list show it as
`cancelled` or `failed` (`last_seq` 0) until it is deleted or the server
restarts, after which it is 404. On shutdown the server sends SIGTERM to
every run process and waits up to 10 s; queued runs stay staged.

The server logs to standard error with stdlib `logging` at
`server.log_level` (`debug`, `info`, `warning`, `error`; also uvicorn's
level): per run `queued (position n)`, `started: run|fork pid <pid>`,
`done`, `cancelled`, `cancelled while queued`, and `failed in <stage>:
<first line>` (warning), each with the run ID, and every standard-error
line of a run process as `run <id>: <line>` (cut to 4000 characters plus
`…`). Settings: `server.host`, `server.port`, `server.max_concurrent_runs`,
`server.static_dir`, `server.log_level`, `server.forwarded_allow_ips`.

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
  exposed to the internet. Behind a local proxy, uvicorn takes the client
  IP and scheme from `X-Forwarded-For` and `X-Forwarded-Proto` only when
  the direct peer is in `server.forwarded_allow_ips` (addresses, networks,
  or `*`; default `["127.0.0.1"]`); the Origin check, the cookie's
  `Secure` flag, and the login limiter use them. A malformed session
  cookie, including a non-ASCII one, is 401.

Settings: `auth.password_hash`, `auth.session_days`, `auth.allowed_origins`.

### Configuration

Precedence: built-in defaults < profile < environment < server global
settings (server runs only) < depth preset < CLI flags or request fields.
The profile name itself is read from the CLI or environment first, then the
profile loads. `config.resolve(profile, overrides, env, depth)` does the
whole resolution in one function and validates once; errors name the source
of the bad value (profile file, environment variable, depth preset file, or
`--set` override).

Depth presets are a per-run axis, separate from profiles:
`src/wosarcher/depths/{quick,standard,deep,exhaustive}.toml`, each with a
one-line `description`. A preset may set only `plan.max_sub_queries`,
`search.max_results`, `fetch.max_pages`, `score.top_k`,
`select.max_context_tokens`, `research.gap_context_tokens`,
`research.rounds`, `research.queries_per_round`, and `write.words`
(`DEPTH_KEYS`); any other key fails when it loads, naming the file and the
key. No built-in preset sets either token budget, so every preset uses
`auto` context and a 4000-token gap budget. The planner decides how many
sub-queries a question needs, so a higher limit costs only when the
question has that many topics.

| key | quick | standard | deep | exhaustive |
|---|---|---|---|---|
| `plan.max_sub_queries` | 3 | - | 6 | 10 |
| `search.max_results` | 5 | - | 10 | 10 |
| `fetch.max_pages` | 15 | - | 60 | 100 |
| `score.top_k` | 6 | - | 10 | 8 |
| `write.words` | 600 | - | 2000 | 3000 |
| `research.rounds` | - | - | 3 | 5 |
| `research.queries_per_round` | - | - | 3 | 4 |

The `research` block: `rounds` (1 to 8, default 1), `queries_per_round`
(default 3), and `gap_context_tokens` (default 4000, or `auto`; see
Research rounds). The `gap` stage
timeout defaults to 180 seconds.

`standard` sets nothing, so it resolves like no depth. `custom` applies no
preset; it only labels a run whose research values the user set. An unknown
name fails before any provider is called and lists the presets.

Environment variables use the prefix `WOSARCHER_` and `__` for nesting
(`WOSARCHER_SCORE__API_KEY`). `--set` values are parsed as TOML values, so
`--set score.top_k=12` is an integer.

Each provider block has the same shape: `provider`, `base_url`, `api_key`,
`model`, `device`, `release` (none, llama-swap, ollama), `fallback_urls`,
`batch_size`, `concurrency`, `connect_timeout`, `timeout`, `retry_budget`
(seconds of retry waits, default 60), `prices` (optional `input_per_mtok`,
`output_per_mtok`, `per_unit` for cost recording). The `llm` block adds
`max_tokens_field` (`max_completion_tokens` or `max_tokens`) and
`reasoning_tokens` (default 0, added to every LLM request's limit, for
reasoning models that count hidden reasoning tokens), and `max_continuations`
(default 2, how often the writer continues a report cut at the output
limit), and `max_output_tokens` (default 8192; caps the writer's output
limit); the `fetch` block adds
`max_pages` (default 40, see Fetch cap and order); the `score` block adds
`rerank_scale` (`auto`, `probability`, `logit`).

A profile may start with a top-level `description` string, one line that
says what it is for. It is file metadata, not a setting: it is not part of
the resolved configuration and cannot be set by environment or `--set`.

`run.preflight` (`off` by default, `cloud`, `all`): before the first stage
the runner probes, as `wosarcher doctor` does, the provider blocks of the
stages it will run (skipped stages and built-in providers excluded; `cloud`
also excludes local blocks). A failed probe ends the run with `run.failed`
naming the first stage that uses the block and an error starting
`preflight: <block>`; no stage starts.

Profiles: `low-vram` (exclusive, small batches; needs llama-swap or Ollama),
`workstation` (shared), `cloud` (no local models, high concurrency;
`llm.reasoning_tokens = 4096` for `gpt-5-mini`). The local profiles set
`llm.timeout = 600`.

The built-in defaults target the smallest setup wosarcher supports well: a
local 32768-token model (a qwen3.5:9b class model behind llama-server or
Ollama) and the `qwen3-embedding:4b` embedder at `num_ctx` 24576.
`llm.context_window` is 32768, `llm.max_output_tokens` 8192 (a quarter of
the window, so a long report cannot claim most of it; exhaustive's
3000-word target asks for 6000), and `llm.timeout` 300 seconds. A larger
model (a 1M-token DeepSeek, a 256k cloud model) sets its own window, output
cap, and timeouts in its profile; the defaults never assume a big window.

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
- `wosarcher profile list` (with each profile's `description`),
  `wosarcher profile show <name>` (resolved, secrets redacted), and
  `wosarcher doctor --profile <name>` make switching safe.

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

The skill is `skill/SKILL.md`. Install it by copying or linking `skill/`
into an agent's skills directory as `wosarcher/`. `tests/test_skill.py`
checks its commands and flags against the typer app, its schema names
against `wosarcher schema`, and its example output against `RunOutput`.

### Evals

The eval harness measures prefilter and scorer choices over the same
inputs. It drives the public CLI only, so it measures what users run.

- `evals/variants.toml` names variants. Each forks from `prefilter` or
  `score` (any other stage is rejected) with a list of `--set` overrides.
  Model variants set `score.fallback=[]` so a broken service fails the
  fork instead of measuring a fallback.
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
  unparsable answer, including a list that is not valid JSON such as
  `[1, 2,]`, records precision as missing and the judge goes on.

The recorded-run fixture is `tests/fixtures/runs/20260101-000000-fixture/`,
tracked in git (only the root `/runs/` is ignored) so tests pass on a fresh
clone, a full `wosarcher run` of the `e2e` profile against recorded SearXNG,
Firecrawl, and LLM responses in `tests/fixtures/http/` (served by the respx
router in `tests/fixtures/recorded.py`; any other request fails naming its
URL). When a contract changes, `test_fixture_parses` names the artifact
that no longer parses; regenerate the fixture with `uv run python -m
tests.fixtures.make_recorded_run`, which replaces its temporary directory
with `/fixture` so the fixture holds no path of the generating machine. `tests/test_e2e_run.py` runs the same
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

Frontend: Vite, React, TypeScript, react-markdown with remark-gfm (tables in
reports), Biome (format and lint);
pnpm. No server-side
rendering: FastAPI serves the static build from the same origin, which keeps
the cookie and `Origin` checks simple. The event and API types are generated
from the Pydantic models (JSON Schema, then json-schema-to-typescript); a
check fails when they drift.

### Frontend design

The visual design is the Claude Design handoff bundle in `design/`. It is
the source of truth for the frontend: the built UI matches it screen by
screen, in both themes and on phone and desktop.

- Primary file: `design/project/wosarcher.dc.html`. Its `scenario`
  values (live, loading, reconnecting, failure, cancelled, finished,
  versions, empty, new, login, login-wrong, login-limited) are the states the
  frontend must implement. The `help` scenario specifies the inline help
  component (the `?` button and its tooltip); it is not a screen.
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

- **Name:** wosarcher everywhere; no version string.
- **Citations:** `[n]` points to a passage; hover shows the passage text,
  source, and score. Citation chips are built from the body with `[n]`
  markers (the streamed text while writing, `report.json` `body` once
  written) and labelled by the client per `citation_marker`, with the
  report writer's author-year fallbacks (web host without `www.`, file
  name, "n.d."); the References list comes from `report.json`.
- **Passage fates:** every card shows one fate, derived in
  `run/fates.ts` from the kept passages of `passages.scored`, `context.json`,
  `select.jsonl`, and `Score.dropped`: cited, kept · selecting (score done,
  select not), ≥ threshold (score not done), source cap, over budget, query
  cap, or below threshold. The Cited | Kept | All filter (default Kept, R
  cycles) lives in the Live screen. `select.jsonl` loads once select is
  done; `scores.jsonl` and `chunks.jsonl` load on the first switch to All,
  joined by `chunk_id`, one card per chunk not kept by any query (its best
  display pair), with display scores from the server's mapping below. Runs
  without `select.jsonl` show uncited kept passages as kept · selecting; a
  missing `dropped` counts as the threshold.
- **Forks:** a fork's log has only `stage.done` events with `copied_from`
  for the stages it copied, each naming the run that ran the stage. The
  browser opens one event stream per distinct `copied_from` and shows that
  run's sub-queries, sources (marked "cached"), and passages for the
  reused phases.
- **Citation options:** two settings, `citation_marker` and
  `reference_style` (see Writing options).
- **Tones:** the 11 tones in Writing options. Default length 1200 words.
- **Scores:** shown as a 0 to 1 bar (`display`). `jev` scores are divided
  by 3; `bm25` scores are divided by the best score of the same query;
  `rerank` shows its mapped score (the sigmoid on the logit scale); other
  scorers are shown as returned; all clamped to 0 to 1.
  The threshold line is `score.min_score / 3` for `jev`,
  `score.relative_threshold` for `bm25`, and `score.relative_threshold`
  times the query's best display score for other scorers. `passthrough`
  pairs have no score bar and no threshold line.
- **Device chip:** shows the stage's `device` label. VRAM figures are not
  shown; no source provides them.
- **GPU policy:** shown from the checked profile, not editable in the
  browser; to change it, edit the profile's `run.gpu_policy`.
- **Prefilter card:** titled Embeddings only for the `embeddings` provider,
  Prefilter otherwise (for example `bm25`). A second line reads "top N per
  sub-query" while running and "top N/sub-query · q4, q5 passthrough" once
  done, with N from the run's `prefilter.top_k` and the IDs from
  `stage.done` `passthrough`.
- **Method tags:** the Plan, Prefilter, Score, Gap, and Write cards show the
  method under the label: the configured provider while running, the one
  that ran after `stage.done`. The tag is the model for LLM and embeddings
  providers, `BM25` for `bm25`, else the provider name. A phase whose
  method (the part before `:`) differs from the configured one is a
  fallback: "<tag> · fallback" in warn style, and its tooltip names the
  configured method and the reason from the stage's warnings. The Passages
  scorer tag decides fallback the same way (`run/providers.ts`).
- **Research rounds:** a multi-round run (resolved `research.rounds` above
  1, read from the run's settings) shows a Gap card between Score and
  Select ("reading round k", "n follow-ups", "ran of N rounds"); loop cards
  add a second line "round k/N" while running, "round k done" between
  rounds, and "n rounds" at the end. The Research rounds panel
  (`screens/live/ResearchRoundsPanel`) replaces Sub-queries: per round its
  queries (collapsed to 2 above 3), new and kept pages or "0 new pages · m
  already fetched", the gap note and follow-up line, then why research
  stopped with the `r-stop` help. The reducer folds `plan.ready`,
  `hit.found`, `page.fetched`, `round.done`, `gap.ready`, and
  `research.done` into `rounds` and `research`. Sources fetched in a later
  round show "round k"; the Report meta line ends with "ran of planned
  rounds".
- **Depth estimate:** "~P pages · R rounds · ~C LLM calls" with P the
  smaller of Max pages and (Sub-queries + 1) × Results per query plus
  (R − 1) × queries per round × Results per query, and C one planner call
  (when Sub-queries > 0) plus R − 1 gap calls plus one writer call.
  Rounds is editable (1-8); files-only runs lock it at 1.
- **Theme:** dark and light both kept; the first visit follows
  `prefers-color-scheme`, and the choice is remembered in the browser.
- **Additions to the prototype:** "Live updates unavailable" is a banner
  styled as the `reconnecting` scenario (warn tint, `ph-wifi-slash`), and
  the footer shows the state with a static warn dot. "Run not found" (Live
  run and Report screens) uses the `empty` scenario's layout with a
  `ph-question` icon. Cancel answered 409 `run_not_active` is not an error:
  the status from the answer is applied and the run refreshed.
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
  it reads `GET /api/runs/{id}` at start and before each reconnect attempt
  and emits each answer as a `summary` update. After any close other than
  1000 or 4404 it reconnects with back-off (2, 4, 8, 16, then 30 s; back to
  2 s once a socket opens) with `since` = the last logged `seq`. It reports
  `connecting`, `connected`, `reconnecting` (attempt N), `replaying` (N
  events, only once the new socket opened), `unavailable` (three sockets in
  a row closed before opening; attempts continue every 30 s), or `closed`
  (with `notFound` on 4404 or a 404 summary, which stops it). An ended
  summary stops it once its `last_seq` is applied or while `unavailable`.
  `runReducer` (`src/run/reducer.ts`) folds events into one `RunView`
  (dedupe by `seq`, except terminal events, which always apply; live-only
  events never move it), `applySummary` sets an ended status from a
  summary, and `useRun` combines them; an ended status is never reopened. The app keeps the followed run's
  stream open on every screen for the Live run dot.
- **State**: React state in `App` behind three contexts (API, auth, UI:
  theme, toast, overlay stack for Escape, followed run, provider warning,
  pending History deletes). No store library.
- **Source dialog**: a passage card in the Live run Passages panel opens
  `screens/live/SourceDialog`, which loads `GET
  /api/runs/{id}/sources/{source_id}` and lists the source's chunks with
  their fates. It is a `components/Dialog`, so Escape goes through the
  overlay stack, and focus returns to the card on close. The why line is
  formatted by `run/sourceFates.ts`.
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
  Patterns used: allowed internal imports, adapters independent in every
  import form with no registry in `adapters/__init__.py`, and no stdlib
  file, process, or network I/O in pure parts (`prompts` may read its own
  files with `importlib.resources`); `tests/test_check_architecture.py`
  tests it.
- Stages are pure; chunking and selection have unit tests.
- Pydantic models document every contract; hot per-chunk paths may use
  `model_construct`.
- Prompts and tones live in `prompts/`, not in Python strings.
- Plain `httpx`; no LangChain.
- End-to-end test with fakes and a recorded run.

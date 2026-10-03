# Design

## Context

core-contracts provides `models.py`, `ports.py`, `config.py` (Settings with
one `Provider` shape per block), `http.py` (`ProviderClient.post_json` with
retries, fallback URLs, a per-provider semaphore, `ProviderError`, and
`UsageLedger`), and the CLI. lexical-bm25 provides `lexical.py`
(`tokenize`, `bm25_scores`, `rank`). Nothing talks to a real provider yet.
See proposal.md for why. Reference implementations (read only):
gpt-researcher v3.6.1-fork `gpt_researcher/context/reranker.py`
(llama-server rerank) and v3.7.0-fork `gpt_researcher/context/jev_filter.py`.

## Goals / Non-Goals

**Goals:**

- Each adapter readable in one sitting: one file, under 200 lines, one
  class, no base class, the wire format visible in the request body.
- All HTTP policy (retry, fallback, concurrency, auth, cancellation) stays
  in `http.py`; adapters only build bodies and parse responses.
- One place, `build.py`, decides which adapter serves which block.

**Non-Goals:**

- Provider auto-detection (guessing llama-server vs vLLM). `base_url`,
  `release`, and `model` say what the endpoint is.
- Streaming for anything but the LLM.

## Decisions

### URL convention: `base_url` includes the API version

Every adapter appends a fixed resource path to `base_url`:

| Adapter | Example `base_url` | Path |
|---|---|---|
| searxng | `http://localhost:8888` | `GET /search` |
| firecrawl | `https://api.firecrawl.dev/v1`, `http://host:3002/v1` | `POST /scrape` |
| embeddings | `http://desktop.lan:8002/v1`, `https://api.openai.com/v1` | `POST /embeddings` |
| rerank | `http://desktop.lan:8001/v1`, `https://api.jina.ai/v1`, `https://api.cohere.com/v2` | `POST /rerank` |
| jev | `https://api.typesafe.ai/v1` | `POST /systemone` |
| llm | `http://localhost:8080/v1` | `POST /chat/completions` |

This matches how OpenAI-compatible clients are configured, so a URL copied
from a provider's docs works, and Cohere's `/v2` needs no special case.
Unload and health endpoints live at the **server root**: `base_url` with a
trailing `/` and then a trailing `/v1` removed (applied to each fallback URL
too). docs/design.md's example `base_url = "http://desktop.lan:8001"` for
rerank becomes `.../v1`.

Alternative: base URLs without version and adapters adding `/v1/...`.
Rejected: Cohere uses `/v2`, and llama-server builds have served rerank at
`/rerank`, `/v1/rerank`, and `/v1/reranking`; putting the version in the
URL lets the user point at whichever exists.

### `http.py` additions

`post_json` becomes a thin wrapper over one loop:

```python
async def request(self, method: str, path: str, *, json: dict | None = None,
                  params: dict | None = None, root: bool = False) -> httpx.Response
async def post_json(self, path, body, *, root=False) -> dict      # request(...).json()
async def get_json(self, path, params=None, *, root=False) -> dict
def stream_lines(self, path: str, body: dict) -> AsyncIterator[str]
```

- `request` is the existing retry, fallback, semaphore, and error loop,
  returning the 2xx response; `root=True` resolves the path against the
  server root. `ProviderError` gains a `status: int | None` attribute (it
  already carries the status in its message) so adapters can react to
  403 or 400 without parsing text.
- `stream_lines` runs the same loop with `http.stream(...)` until a 2xx
  response arrives, then, still holding the semaphore slot, yields the
  `data:` payload of each server-sent event line (blank lines and comments
  skipped). It is an async generator inside `async with`, so closing the
  generator (consumer stops, or task cancelled) closes the response and
  frees the slot. A transport error after the first line raises
  `ProviderError` with no retry.
- Two plain functions, used by adapters and the doctor:

```python
async def unload(client: ProviderClient, release: str, model: str) -> None
async def unload_supported(client: ProviderClient, release: str) -> bool
```

  `unload`: `llama-swap` → `request("GET", "/unload", root=True)`;
  `ollama` → `post_json("/api/generate", {"model": model, "keep_alive": 0},
  root=True)`; `none` → return. llama-swap's `/unload` unloads every model
  on that server, which is what exclusive mode wants for a device.
  `unload_supported`: `GET /running` (llama-swap) or `GET /api/version`
  (Ollama) at the root, `True` on 2xx, `False` on `ProviderError`.

These live in `http.py` because adapters may not import each other and the
logic is the same for every model adapter.

Alternative: a shared base class for model adapters. Rejected: the project
avoids inheritance; two functions are enough.

### `config.py` additions

```python
class SearchConfig(Provider):
    max_results: int = Field(10, ge=1)
    language: str = ""                                   # empty: not sent
    time_range: Literal["", "day", "week", "month", "year"] = ""

class FetchConfig(Provider):
    max_chars: int = Field(50_000, ge=1)
    only_main_content: bool = True
    page_timeout: float = 45.0                           # must be < timeout
```

- `Provider.concurrency: int | None = None`. `build.py` fills `None` from
  `config.DEFAULT_CONCURRENCY = {"searxng": 4, "firecrawl": 6, "embeddings": 4,
  "rerank": 4, "jev": 64, "llm": 1}` before creating the `ProviderClient`.
  A plain default of 4 cannot tell "not set" from "set to 4", and Jev
  needs 64 while a local LLM needs 1 (design.md, Adapters).
- `ScoreConfig.fallback: list[Literal["bm25", "passthrough"]]`.
- `RunConfig.gpu_policy: Literal["shared", "exclusive"] = "shared"`
  (added if core-contracts did not define it).
- A `Provider` model validator: `release = "ollama"` requires a non-empty
  `model`; a `FetchConfig` validator: `page_timeout < timeout`.
- `Settings.search: SearchConfig`, `Settings.fetch: FetchConfig`.

### `models.py` and `ports.py` additions

```python
class EmbedderInfo(BaseModel):          # frozen, extra="forbid"
    model: str
    dimension: int

class ProviderHealth(BaseModel):
    block: str                           # search | fetch | prefilter | score | llm
    provider: str
    base_url: str                        # "" for built-in
    device: str | None
    status: Literal["ok", "failed", "built-in"]
    model: str | None
    latency_ms: float | None
    unload: Literal["yes", "no", "n/a"]
    error: str | None

class DoctorReport(BaseModel):
    providers: list[ProviderHealth]
    warnings: list[str]
```

`ports.py`: `Embedder` gains `async def describe(self) -> EmbedderInfo`, and
a new Protocol:

```python
class Managed(Protocol):
    async def probe(self) -> ProviderHealth: ...
    async def release(self) -> None: ...
```

`ProviderHealth` and `DoctorReport` are contracts because server-api
returns them from `GET /providers/health` and the frontend generates types
from `wosarcher schema`.

### Adapters

Each adapter is a class taking `(cfg, client: ProviderClient | None,
ledger: UsageLedger, stage: str)` and recording usage with
`ledger.record(cfg.provider, stage, ...)` after each successful request.
Each HTTP adapter implements `probe()` (time one small request with
`time.perf_counter`, catch `ProviderError` into `status="failed"`, fill
`unload` with `unload_supported` when `release != "none"`) and `release()`
(calls `unload`; a no-op for SearXNG and Firecrawl).

- **searxng.py** `SearxngSearcher.search(query)`: `get_json("/search",
  params)`; skip results without `url`; dedupe by
  `models.normalise_url` (core-contracts' URL normaliser); cap; build
  `Hit`s ranked from 1. Catches `ProviderError` with `status == 403` and
  re-raises with the "enable the `json` format in SearXNG `search.formats`"
  hint.
- **firecrawl.py** `FirecrawlFetcher.fetch(url)`: body as in the spec;
  checks `success`, `metadata.statusCode`, empty markdown; cuts to
  `max_chars`; builds a `Page` with a web `Source`. Units from
  `metadata.creditsUsed` or 1.
- **embeddings.py** `OpenAIEmbedder.embed(texts)`: split into batches,
  `asyncio.gather` one task per batch (the client semaphore limits
  concurrency), concatenate. Decoding base64 uses the standard library:
  `array.array("f", base64.b64decode(s))`, `byteswap()` when
  `sys.byteorder == "big"`. The instance attributes `_base64: bool = True`
  and `_info: EmbedderInfo | None` are the only state. `describe()`
  returns `_info`, embedding `["wosarcher"]` first when it is `None`;
  an `asyncio.Lock` makes concurrent first calls send one request.
- **rerank.py** `RerankScorer` (`name = "rerank"`, `calibrated = False`):
  body `{"query", "documents", "model"?}`. No `top_n` and no
  `return_documents`: providers disagree on those names (Voyage uses
  `top_k`), and every provider returns all documents when `top_n` is
  absent. Reads `results` or `data`.
- **jev.py** `JevScorer` (`name = "jev"`, `calibrated = True`): one request
  per chunk via `asyncio.gather`. The question comes from
  `src/wosarcher/prompts/jev.toml`:

  ```toml
  instructions = "How useful is this passage for answering the question: $query"
  criteria = [
    "Unrelated to the question",
    "Same topic, but does not help answer the question",
    "Partially answers the question or gives useful supporting facts",
    "Directly answers the question with specific facts",
  ]
  ```

  loaded once in `__init__` with `importlib.resources` and `tomllib`;
  `string.Template(...).safe_substitute(query=query.text)`. The chunk
  text goes into `state` untouched. 429 and 529 retries come from
  `ProviderClient`.
- **bm25.py** `Bm25Scorer` (`name = "bm25"`, `calibrated = False`):
  `lexical.bm25_scores`, divide by the best; when the best is 0, the first
  `max_results` (25) chunks get 1.0. No client, no usage, no `Managed`.
- **passthrough.py** `PassthroughScorer` (`name = "passthrough"`,
  `calibrated = False`): every value 1.0. Selection (passage-ranking)
  orders equal scores by input position, so input order is kept.
- **llm.py** `ChatLLM.complete` and `ChatLLM.stream`: body
  `{"messages", "max_tokens", "stream", "model"?}`; streaming adds
  `stream_options.include_usage`, parses each `stream_lines` payload with
  `json.loads`, stops at `[DONE]`, and records usage when the generator
  finishes (in a `finally`, so an early stop still counts the request).
- **fakes.py**: `FakeSearcher` (hits by query text), `FakeFetcher` (pages
  by URL, a set of failing URLs), `FakeEmbedder` (deterministic vectors
  from a SHA-256 of the text, `describe()` → `fake-embed`, 8), `FakeScorer`
  (name, calibrated, values from a dict or a constant), `FakeLLM` (scripted
  replies; `stream` yields the reply word by word; records messages). Each
  fake records calls in a list and implements `probe()` and `release()`
  (counting releases). Fakes hold no network code and import only models
  and ports.

### Composition root: `build.py`

`Adapters` (below) is a bundle of ports, so it lives in `ports.py`, and
`DEFAULT_CONCURRENCY` lives in `config.py`. The runner can then accept an
`Adapters` and read default concurrency without importing `build`; only
`build`, `server`, and `cli` depend on the composition root.

```python
@dataclass(frozen=True)
class Adapters:
    searcher: Searcher
    fetcher: Fetcher
    embedder: Embedder | None          # None when prefilter.provider is "bm25" or "none"
    scorers: dict[str, Scorer]         # score.provider, then each score.fallback, in order
    planner: LLM
    writer: LLM
    managed: dict[str, Managed]        # block name -> adapter, remote blocks only

SCORERS: dict[str, Callable[[ScoreConfig, ProviderClient | None, UsageLedger], Scorer]] = {
    "rerank": ..., "jev": ..., "bm25": ..., "passthrough": ...,
}

def build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters
```

The allowed `provider` values per block are `search: searxng`,
`fetch: firecrawl`, `prefilter: embeddings | bm25 | none`,
`score: rerank | jev | bm25`, `llm: llm`; any other value raises
`ValueError("score.provider 'x' is not one of: rerank, jev, bm25")`
before any client is created. One `ProviderClient` per remote block; the
planner (`stage="plan"`) and writer (`stage="write"`) share the `llm`
client, so they share its semaphore. The constructor dicts are module
constants (data), not a registry: nothing registers into them at runtime.

### Doctor: `doctor.py` and the CLI

```python
async def check(settings: Settings, managed: Mapping[str, Managed]) -> DoctorReport
def exclusive_warnings(settings: Settings) -> list[str]
```

`doctor` takes `Adapters.managed`, not `Adapters`, so it does not import
`build` and keeps its layering small.
`check` runs every probe with `asyncio.gather`, adds `built-in` rows for
`bm25`/`passthrough` blocks, adds a warning for each probe with
`unload == "no"` while `release != "none"`, and appends
`exclusive_warnings`. `exclusive_warnings` groups remote blocks by
`device`, and warns for each block with `release == "none"` in a group of
two or more when `run.gpu_policy == "exclusive"`. `doctor` imports only
`models`, `ports`, and `config` (new `ALLOWED` entry); `cli.py` composes
`resolve` → `build` → `doctor.check` and renders a rich table or JSON.
The exit code is 1 when any row has `status == "failed"`.

### Tests

`tests/adapters/test_<adapter>.py` per adapter with respx routes, one test
per spec scenario; `tests/test_build.py`, `tests/test_doctor.py` (fakes),
`tests/test_cli_doctor.py` (typer `CliRunner`, respx, temporary
`XDG_CONFIG_HOME` profile). No test touches the network.

## Risks / Trade-offs

- [The Firecrawl probe spends one cloud credit] → Documented in the doctor
  help text; self-hosted Firecrawl is free.
- [llama-swap `/unload` unloads every model on that server, not just one]
  → Intended for exclusive mode on a shared device; per-model unload can
  come later if needed.
- [Retrying an embeddings batch without base64 on any 400 also retries
  real input errors once] → One extra request, then the same error
  surfaces.
- [Rerank scores are not comparable across providers] → They are
  uncalibrated by declaration; selection uses a relative threshold.
- [Jev sends one request per chunk] → Concurrency 64 and the prefilter's
  top-K bound the count; cost is recorded per run.
- [`release = "ollama"` on a rerank block] → Ollama has no rerank API, so
  the probe of that block already fails and the doctor shows it.

# Design

## Context

The repository has only a Nix flake, docs, and OpenSpec setup; there is no
Python code yet. docs/design.md describes the whole system. This change
builds the parts every later change imports: contracts, ports,
configuration, and the provider HTTP client. See proposal.md for scope.

## Goals / Non-Goals

**Goals:**

- Types that later adapters and stages can be written against without
  changes to this code.
- Configuration that can be read top to bottom by a person: one module, one
  resolution function, no hidden sources.
- An HTTP client whose retry and fallback behaviour is visible in one short
  function.

**Non-Goals:**

- Hot reload of configuration inside a long-running process. Each run
  resolves configuration once at start (the server will spawn `wosarcher run` per
  run).
- Price tables for cloud providers. Prices are configuration, not code.

## Decisions

### Package layout: `src/wosarcher`, CLI command `wosarcher`

`uv init --package` uses the src layout, which keeps tests from importing
the working tree by accident. The package, the CLI command, and the
environment prefix (`WOSARCHER_`) all use the project name, so there is one
name to remember.

```
src/wosarcher/
  models.py      # contracts and ID helpers
  ports.py       # Protocols
  config.py      # settings models, profile loading, resolve()
  http.py        # ProviderClient, Usage, UsageLedger
  cli.py         # typer app: profile, schema
  profiles/      # built-in low-vram.toml, workstation.toml, cloud.toml
tests/
```

### Contracts: frozen Pydantic models with `extra="forbid"`

Frozen models make stage outputs safe to share; `extra="forbid"` turns typos
in JSON or TOML into errors. Alternative: dataclasses. Rejected for
contracts because Pydantic gives validation, JSON round trips, and JSON
Schema in one place; hot paths may use `model_construct` later if profiling
shows a need.

IDs are the first 16 hex characters of a SHA-256 over a fixed string:

- web `source_id`: `sha256("web\n" + normalised_url)`
- file `source_id`: `sha256("file\n" + content_sha256)`
- `chunk_id`: `sha256(source_id + "\n" + str(position) + "\n" + text)`

64 bits is enough for the number of chunks in one run; the prefix keeps IDs
readable in logs and JSONL.

URL normalisation uses `urllib.parse` from the standard library; no
dependency.

### Ports: `typing.Protocol` with async methods

```python
class Searcher(Protocol):
    async def search(self, query: Query) -> list[Hit]: ...

class Fetcher(Protocol):
    async def fetch(self, url: str) -> Page: ...

class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class Scorer(Protocol):
    name: str
    calibrated: bool
    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]: ...

class LLM(Protocol):
    async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion: ...
    def stream(self, messages: list[Message], *, max_tokens: int) -> AsyncIterator[str]: ...
```

Structural typing means adapters and fakes need no base class. Alternative:
abstract base classes. Rejected: inheritance adds nothing here and the
design avoids it. `release()` is not in this change; it arrives with the
adapters that support it.

### Configuration: explicit resolution in one function

```python
def resolve(profile: str | None, overrides: list[str], env: Mapping[str, str]) -> Settings
```

1. Pick the profile name: argument, `WOSARCHER_PROFILE`, the `current` file, then
   `workstation`.
2. Load the profile TOML (user directory first, then built-in).
3. Read `WOSARCHER_*` variables into a nested dict.
4. Parse `--set` overrides into a nested dict.
5. Deep-merge defaults < profile < env < overrides, then validate once with
   `Settings.model_validate`.

Each layer keeps a record of where each key came from, so validation errors
can name the source (spec: Validation).

Alternative: pydantic-settings' source chain (`settings_customise_sources`).
Rejected for resolution because the two-pass profile selection and
per-source error messages fight its design, and the whole precedence chain
would be hidden in framework hooks. pydantic-settings is therefore not a
dependency; the standard library `tomllib` reads TOML. This is a change from
docs/design.md, which named pydantic-settings; update it.

`--set` values are parsed as TOML values (`12` is an integer, `"x"` or bare
`x` is a string, `[..]` a list), so typing follows the field through
validation.

Secrets are `SecretStr`. Serialising configuration for display or
artifacts uses one function that replaces every set secret with `***`.

### Settings shape

```python
class Prices(BaseModel):     # all optional
    input_per_mtok: float | None
    output_per_mtok: float | None
    per_unit: float | None

class Provider(BaseModel):   # shared shape (spec: Provider block shape)
    provider: str
    base_url: str = ""
    api_key: SecretStr | None = None
    model: str = ""
    device: str | None = None
    release: Literal["none", "llama-swap", "ollama"] = "none"
    fallback_urls: list[str] = []
    batch_size: int = 16
    concurrency: int = 4
    connect_timeout: float = 3.0
    timeout: float = 60.0
    prices: Prices = Prices()

class ScoreConfig(Provider):
    min_score: float | None = None
    relative_threshold: float = 0.5
    top_k: int = 10
    fallback: list[str] = ["bm25", "passthrough"]

class Settings(BaseModel):
    search: Provider
    fetch: Provider
    prefilter: Provider
    score: ScoreConfig
    llm: Provider
    chunk: ChunkConfig
    select: SelectConfig
    run: RunConfig
    write: WritingOptions
```

Stage-specific blocks extend `Provider` with only the fields that stage
needs. One level of inheritance on configuration models is the exception to
the no-inheritance rule, because it states the shared shape directly.

### HTTP: one `ProviderClient` per configured provider

```python
class ProviderClient:
    def __init__(self, name: str, cfg: Provider, http: httpx.AsyncClient, usage: UsageLedger): ...
    async def post_json(self, path: str, body: dict) -> dict: ...
```

`post_json` holds the whole policy in one loop: for each URL (base, then
fallbacks), acquire the semaphore, send, retry retryable statuses with
backoff and `Retry-After`, move to the next URL only on connection failure.
About 60 lines, readable top to bottom.

Alternatives: tenacity or httpx transports with retry. Rejected: the
fallback rule (status does not fall back, connection failure does) is
specific, and a hand-written loop is shorter than configuring a library to
do it.

One `httpx.AsyncClient` is shared by all providers for connection pooling.
Errors are a single `ProviderError` with provider name, URL, status, and a
short body excerpt; the API key is never included.

### Usage recording

`UsageLedger.record(provider, stage, input_tokens=0, output_tokens=0,
units=0)` sums per (provider, stage) and computes cost from the provider's
`prices`. The ledger is a plain object passed in by the composition root;
there is no global.

### CLI

typer app with `profile list|show|use` and `schema`. `wosarcher schema` builds one
document with `pydantic.json_schema.models_json_schema` over all contract
types and prints it with sorted keys.

## Risks / Trade-offs

- [Own config resolution instead of pydantic-settings] → More code to own
  (about 100 lines). Mitigation: it is one function with tests per
  precedence rule, and errors name their source.
- [Truncated 64-bit IDs] → Collisions are possible in theory. Mitigation:
  negligible at run scale; the run store can assert uniqueness.
- [basedpyright strict with Pydantic] → Some friction with generics.
  Mitigation: keep any `type: ignore` local, with a comment saying why.
- [Retry on 529 and `Retry-After`] → A long `Retry-After` can stall a run.
  Mitigation: cap the wait at the provider's `timeout`.

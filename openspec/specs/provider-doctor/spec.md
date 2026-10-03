# provider-doctor Specification

## Purpose

Lets a user check, before a run, that every configured provider answers,
which model it serves, how fast it is, and whether it can unload models;
and lets the runner release a model when GPU use is exclusive.

## Requirements

### Requirement: Doctor command
`wosarcher doctor` SHALL check the providers of the resolved configuration
(it accepts `--profile` and `--set` like other commands) and print one row
per configured block (`search`, `fetch`, `prefilter`, `score`, `llm`):
provider, base URL, device, status, model name, latency of one small
request in milliseconds, and unload support (`yes`, `no`, or `n/a` when
`release = "none"`). Built-in providers (`bm25`, `passthrough`) SHALL be
shown as built in, without a request. Probes SHALL run concurrently.
`--json` SHALL print the same report as JSON. The command SHALL exit 1 when
any probe fails and 0 otherwise, warnings included.

#### Scenario: All healthy
- **WHEN** every configured endpoint answers its probe
- **THEN** each row shows status ok, the model name, and a latency, and the exit code is 0

#### Scenario: One endpoint down
- **WHEN** the score endpoint and its fallback URLs refuse connections
- **THEN** the score row shows the failure with every URL tried, the other rows are still checked, and the exit code is 1

#### Scenario: Built-in scorer
- **WHEN** `score.provider = "bm25"`
- **THEN** the score row says built in and no request is sent for it

#### Scenario: Other profile
- **WHEN** the user runs `wosarcher doctor --profile cloud`
- **THEN** the providers of the `cloud` profile are checked, not the active profile

### Requirement: Probes
Each probe SHALL make one small real request through the adapter:
SearXNG a one-word search, Firecrawl a scrape of `https://example.com`,
embeddings one short text, rerank one query with one document, Jev one
short passage, and the LLM a one-token completion. The model name SHALL be
the one the endpoint reports when it reports one, otherwise the configured
model. Probes SHALL use the provider's own timeouts and fallback URLs.

#### Scenario: Reported model shown
- **WHEN** the LLM endpoint answers the probe with `model: "qwen3-8b-q4_k_m"`
- **THEN** the llm row shows `qwen3-8b-q4_k_m`

### Requirement: Unload support check
When a block sets `release = "llama-swap"`, the doctor SHALL report unload
support as `yes` when `GET <server root>/running` answers 2xx; for
`release = "ollama"`, when `GET <server root>/api/version` answers 2xx;
otherwise `no`. The server root is `base_url` without a trailing `/v1`.

#### Scenario: llama-swap detected
- **WHEN** `score.base_url = "http://desktop.lan:8080/v1"`, `release = "llama-swap"`, and `GET http://desktop.lan:8080/running` answers 200
- **THEN** the score row shows unload support `yes`

#### Scenario: Plain llama-server
- **WHEN** `release = "llama-swap"` but `/running` answers 404
- **THEN** unload support is `no` and a warning says the endpoint cannot unload

### Requirement: Exclusive GPU warnings
When `run.gpu_policy = "exclusive"`, the doctor SHALL warn for each block
that has `release = "none"` and shares its `device` label with another
block, naming the block and the device and saying that `llama-swap` or
`ollama` is needed. Blocks without a device, or alone on their device,
SHALL NOT be warned about.

#### Scenario: Shared device without release
- **WHEN** gpu policy is exclusive, `score.device` and `llm.device` are both `laptop:gpu0`, and `score.release = "none"`
- **THEN** the doctor warns about `score` on `laptop:gpu0`

#### Scenario: Separate devices
- **WHEN** gpu policy is exclusive, `score.device = "desktop:gpu0"`, `llm.device = "laptop:gpu0"`, and both have `release = "none"`
- **THEN** no exclusive-mode warning is printed

#### Scenario: Shared policy
- **WHEN** gpu policy is shared
- **THEN** no exclusive-mode warning is printed

### Requirement: Model release
Every remote adapter SHALL offer a release operation. With
`release = "llama-swap"` it SHALL send `GET <server root>/unload`; with
`release = "ollama"` it SHALL send `POST <server root>/api/generate` with
the configured `model` and `keep_alive: 0`; with `release = "none"`, and
for adapters with no model (SearXNG, Firecrawl), it SHALL do nothing and
send no request. A failed release SHALL raise a provider error and leave
the adapter usable.

#### Scenario: llama-swap unload
- **WHEN** an adapter with `base_url = "http://desktop.lan:8080/v1"` and `release = "llama-swap"` is released
- **THEN** `GET http://desktop.lan:8080/unload` is sent

#### Scenario: Ollama unload
- **WHEN** an LLM adapter with `release = "ollama"` and `model = "qwen3:8b"` is released
- **THEN** `POST <server root>/api/generate` is sent with `model: "qwen3:8b"` and `keep_alive: 0`

#### Scenario: No release configured
- **WHEN** an adapter with `release = "none"` is released
- **THEN** no request is sent

#### Scenario: Ollama without a model
- **WHEN** a profile sets `release = "ollama"` on a block with no `model`
- **THEN** resolution fails naming the block's `model` field

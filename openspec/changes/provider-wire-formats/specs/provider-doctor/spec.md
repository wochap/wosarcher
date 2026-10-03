## MODIFIED Requirements

### Requirement: Probes
Each probe SHALL make one small real request through the adapter:
SearXNG a one-word search, Firecrawl a scrape of `https://example.com`,
embeddings one short text, rerank one query with one document, Jev one
short passage, and the LLM a one-token completion. The model name SHALL be
the one the endpoint reports when it reports one, otherwise the configured
model. Probes SHALL use the provider's own timeouts and fallback URLs. The
rerank probe SHALL report its raw score and the scale it implies as a note
on its row: `probe score <value> (probability scale)` when the value is
between 0 and 1, otherwise `probe score <value> (logit scale)`; with
`score.rerank_scale` set to `probability` or `logit`, the note names the
configured scale instead.

#### Scenario: Reported model shown
- **WHEN** the LLM endpoint answers the probe with `model: "qwen3-8b-q4_k_m"`
- **THEN** the llm row shows `qwen3-8b-q4_k_m`

#### Scenario: Logit reranker
- **WHEN** the rerank endpoint answers the probe with `relevance_score: -3.25` and `score.rerank_scale = "auto"`
- **THEN** the score row's note is `probe score -3.25 (logit scale)`

## ADDED Requirements

### Requirement: Context window check
After a successful LLM probe, the doctor SHALL ask the server for its
context size: `GET <server root>/props` and, when that does not answer and
`llm.model` is set, `GET <server root>/upstream/<model>/props` (llama-swap).
It SHALL read `default_generation_settings.n_ctx`, or a top-level `n_ctx`,
and show it on the llm row. When it is below `llm.context_window`, the
doctor SHALL add a warning naming both numbers and saying to start the
server with a larger context (llama-server `-c`) or to lower
`llm.context_window`. A server that exposes no such endpoint SHALL get no
warning and no error. The warning SHALL NOT change the exit code.

#### Scenario: Context too small
- **WHEN** `llm.context_window = 32768` and `GET <root>/props` answers `{"default_generation_settings": {"n_ctx": 4096}}`
- **THEN** the doctor warns that the server context 4096 is below `llm.context_window` 32768, and the exit code is 0 when every probe succeeded

#### Scenario: Context large enough
- **WHEN** `llm.context_window = 16384` and the server reports `n_ctx = 32768`
- **THEN** no context warning is printed and the llm row shows 32768

#### Scenario: Cloud API
- **WHEN** the LLM endpoint answers 404 to both `props` requests
- **THEN** the llm row has no context size and the doctor prints no context warning

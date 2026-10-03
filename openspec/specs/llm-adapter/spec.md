# llm-adapter Specification

## Purpose

Plans and writes through any OpenAI-compatible chat endpoint (llama-server,
Ollama, vLLM, or a cloud API), with complete and streaming calls and token
usage per stage.

## Requirements

### Requirement: Chat completion
The LLM adapter SHALL send `POST <base_url>/chat/completions` with the
messages (role and content), `max_tokens`, `stream: false`, and `model`
when configured, and SHALL return the first choice's message content
(empty when the content is null) with the input and output token counts
from `usage`.

#### Scenario: Completion returned
- **WHEN** the endpoint answers with content `Plan: ...` and usage 120 prompt and 30 completion tokens
- **THEN** the completion text is `Plan: ...` with 120 input and 30 output tokens

#### Scenario: Null content
- **WHEN** the first choice has `content: null`
- **THEN** the completion text is empty

### Requirement: Streaming
Streaming SHALL send the same request with `stream: true` and
`stream_options: {"include_usage": true}`, read server-sent events, and
yield each non-empty `choices[0].delta.content` in order until `[DONE]` or
the end of the stream. Events without choices (the usage event) SHALL
yield nothing. Retries and fallback URLs SHALL apply only before the first
event arrives; an error after that SHALL fail the stream. Stopping the
consumer SHALL close the HTTP response.

#### Scenario: Deltas in order
- **WHEN** the stream carries deltas `Hel`, `lo`, an empty delta, then a usage event and `[DONE]`
- **THEN** the adapter yields `Hel` then `lo`

#### Scenario: Error mid-stream
- **WHEN** the connection drops after the first delta
- **THEN** the stream fails with a provider error and no request is retried

#### Scenario: Consumer stops early
- **WHEN** the consumer stops reading after the first delta
- **THEN** the HTTP response is closed and the concurrency slot is released

### Requirement: LLM usage per stage
Planning and writing SHALL use separate LLM adapters on the same provider
client, one recording usage under stage `plan` and one under `write`,
sharing one concurrency limit (default 1). Streaming SHALL record the usage
event's tokens, or zero tokens when the server sends none; the request is
still counted.

#### Scenario: Separate stages
- **WHEN** the planner uses 100 input tokens and the writer 900
- **THEN** the ledger shows 100 for stage `plan` and 900 for stage `write`

#### Scenario: Shared limit
- **WHEN** `llm.concurrency` is not set and the planner and the writer call at the same time
- **THEN** the second call waits until the first finishes

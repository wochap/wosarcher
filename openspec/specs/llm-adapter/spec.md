# llm-adapter Specification

## Purpose

Plans and writes through any OpenAI-compatible chat endpoint (llama-server,
Ollama, vLLM, or a cloud API), with complete and streaming calls and token
usage per stage.

## Requirements

### Requirement: Chat completion
The LLM adapter SHALL send `POST <base_url>/chat/completions` with the
messages (role and content), the output token limit, `stream: false`, and
`model` when configured, and SHALL return the first choice's message
content (empty when the content is null) with the input and output token
counts from `usage`. The output token limit SHALL be sent as
`max_completion_tokens` by default, or as `max_tokens` when
`llm.max_tokens_field = "max_tokens"`; never both. The value sent SHALL be
the caller's limit plus `llm.reasoning_tokens` (default 0), so reasoning
models, which count hidden reasoning tokens against the limit, still have
room for text. When the answer has empty content and finish reason
`length`, the call SHALL fail with a provider error that names
`llm.reasoning_tokens`.

#### Scenario: Completion returned
- **WHEN** the endpoint answers with content `Plan: ...` and usage 120 prompt and 30 completion tokens
- **THEN** the completion text is `Plan: ...` with 120 input and 30 output tokens

#### Scenario: Null content
- **WHEN** the first choice has `content: null`
- **THEN** the completion text is empty

#### Scenario: Default limit field
- **WHEN** the planner calls the LLM with a limit of 512 and `llm.max_tokens_field` is not set
- **THEN** the request body has `max_completion_tokens: 512` and no `max_tokens`

#### Scenario: Reasoning allowance added
- **WHEN** `llm.reasoning_tokens = 4096` and the planner calls with a limit of 512
- **THEN** the request body has `max_completion_tokens: 4608`

#### Scenario: Limit spent on reasoning
- **WHEN** the endpoint answers with `content: ""` and `finish_reason: "length"`
- **THEN** the call fails with a provider error that names `llm.reasoning_tokens`

#### Scenario: Legacy limit field
- **WHEN** `llm.max_tokens_field = "max_tokens"` and the planner calls with a limit of 512
- **THEN** the request body has `max_tokens: 512` and no `max_completion_tokens`

### Requirement: Streaming
Streaming SHALL send the same request with `stream: true` and
`stream_options: {"include_usage": true}`, read server-sent events, and
yield each non-empty `choices[0].delta.content` in order until `[DONE]` or
the end of the stream. Events without choices (the usage event) SHALL
yield nothing. An event with an `error` member SHALL fail the stream with a
provider error that includes the error's `message` (or the error as text).
When the stream ends, the adapter SHALL report the last non-null
`choices[0].finish_reason` it saw (or none) to the caller's finish
callback. When the stream ends with finish reason `length` and yielded no
content, it SHALL fail with a provider error that names
`llm.reasoning_tokens`. Retries and fallback URLs SHALL apply only before the first event
arrives; an error after that SHALL fail the stream. Stopping the consumer
SHALL close the HTTP response.

#### Scenario: Deltas in order
- **WHEN** the stream carries deltas `Hel`, `lo`, an empty delta, then a usage event and `[DONE]`
- **THEN** the adapter yields `Hel` then `lo`

#### Scenario: Error mid-stream
- **WHEN** the connection drops after the first delta
- **THEN** the stream fails with a provider error and no request is retried

#### Scenario: Error event mid-stream
- **WHEN** after two deltas the server sends `data: {"error": {"message": "the request exceeds the available context size"}}`
- **THEN** the stream fails with a provider error whose text includes `exceeds the available context size`

#### Scenario: Finish reason reported
- **WHEN** the last content event has `finish_reason: "length"`
- **THEN** the finish callback receives `length` after the last delta

#### Scenario: Stream with no text at the limit
- **WHEN** a stream carries only a usage event and a final event with `finish_reason: "length"` and no content
- **THEN** the stream fails with a provider error that names `llm.reasoning_tokens`

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

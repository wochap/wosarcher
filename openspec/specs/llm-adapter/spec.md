# llm-adapter Specification

## Purpose

Plans and writes through any OpenAI-compatible chat endpoint (llama-server,
Ollama, vLLM, or a cloud API), with complete and streaming calls and token
usage per stage.

## Requirements

### Requirement: Chat completion
The LLM adapter (`llm.provider = "openai"`) SHALL send
`POST <base_url>/chat/completions` with the messages (role and content),
`stream: false`, `model` when configured, and the thinking fields of
Requirement: Thinking effort, and SHALL return the first choice's message
content (empty when the content is null) with the input and output token
counts from `usage`. When a token cap is sent, it SHALL be the caller's
limit, as `max_completion_tokens` by default or as `max_tokens` when
`llm.max_tokens_field = "max_tokens"`; never both. When the answer has
empty content and finish reason `length`, the call SHALL fail with a
provider error that names the step's `llm.reasoning.<step>` setting, says
to set it to `none`, and gives the limit when one was sent.

#### Scenario: Completion returned
- **WHEN** the endpoint answers with content `Plan: ...` and usage 120 prompt and 30 completion tokens
- **THEN** the completion text is `Plan: ...` with 120 input and 30 output tokens

#### Scenario: Null content
- **WHEN** the first choice has `content: null`
- **THEN** the completion text is empty

#### Scenario: Default limit field
- **WHEN** the planner calls the LLM with a limit of 512 and effort `none`, and `llm.max_tokens_field` is not set
- **THEN** the request body has `max_completion_tokens: 512` and no `max_tokens`

#### Scenario: Reasoning allowance added
- **WHEN** the planner calls with a limit of 512 and effort `low`
- **THEN** the request body has `reasoning_effort: "low"` and no token cap field, and no allowance is added to any limit

#### Scenario: Limit spent on reasoning
- **WHEN** the writer's call with effort `low` is answered with `content: ""` and `finish_reason: "length"`
- **THEN** the call fails with a provider error that names `llm.reasoning.write` and says to set it to `none`

#### Scenario: Legacy limit field
- **WHEN** `llm.max_tokens_field = "max_tokens"` and the planner calls with a limit of 512 and effort `none`
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
content, it SHALL fail with a provider error that names the step's
`llm.reasoning.<step>` setting and says to set it to `none`. Retries and
fallback URLs SHALL apply only before the first event arrives; an error
after that SHALL fail the stream. Stopping the consumer SHALL close the
HTTP response.

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
- **WHEN** the writer streams with effort `high` and the stream carries only a usage event and a final event with `finish_reason: "length"` and no content
- **THEN** the stream fails with a provider error that names `llm.reasoning.write`

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

### Requirement: Thinking effort
Every completion and stream call SHALL carry an effort, one of `none`,
`low`, `medium`, `high`, or `default`, chosen by the caller (the stage's
`llm.reasoning.<step>` value; `none` for the eval judge). The adapter
SHALL send, per effort:
- `none`: `reasoning_effort: "none"` and the token cap equal to the
  caller's limit, so visible text is all the cap covers;
- `low`, `medium`, `high`: `reasoning_effort` set to that level and no
  token cap field at all; the server resolves the budget from the model's
  own limits;
- `default`: neither `reasoning_effort` nor a token cap field.

When the endpoint answers HTTP 400 whose body names `reasoning_effort`,
the call SHALL fail with a provider error that says the server rejects
`reasoning_effort` and to set `llm.reasoning.<step> = "default"`.

#### Scenario: No thinking
- **WHEN** the gap step calls with effort `none` and a limit of 768
- **THEN** the request body has `reasoning_effort: "none"` and `max_completion_tokens: 768`

#### Scenario: Thinking level
- **WHEN** the writer streams with effort `high` and a limit of 2400
- **THEN** the request body has `reasoning_effort: "high"` and neither `max_completion_tokens` nor `max_tokens`

#### Scenario: Server default
- **WHEN** the planner calls with effort `default`
- **THEN** the request body has no `reasoning_effort`, no `max_completion_tokens`, and no `max_tokens`

#### Scenario: Server rejects the field
- **WHEN** the endpoint answers 400 with a body naming `reasoning_effort`
- **THEN** the call fails with a provider error that names `reasoning_effort` and says to set `llm.reasoning.plan = "default"` for the planner's call

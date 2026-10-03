# provider-http Specification

## Purpose

Defines how wosarcher calls HTTP providers (local, on another LAN machine, or
in the cloud): timeouts, retries, concurrency limits, fallback endpoints,
and usage recording.

## Requirements

### Requirement: Timeouts
Every provider request SHALL use the provider's `connect_timeout` (default
3 seconds) for establishing the connection and its `timeout` for the whole
request.

#### Scenario: Unreachable host fails fast
- **WHEN** a provider's host does not accept connections
- **THEN** the request fails within the connect timeout, not the request timeout

### Requirement: Retries
Requests SHALL be retried on the same URL on HTTP 429, 502, 503, 504, and
529 with exponential backoff (0.5 s, then doubling, each wait at most 8 s).
A `Retry-After` header SHALL be respected when present. Retries SHALL
continue while the total time spent waiting on that URL stays within the
block's `retry_budget` (default 60 seconds) and at most 10 retries have
been made; a wait that would exceed the budget SHALL NOT be started, and
the call then fails. `retry_budget = 0` SHALL disable retries. Other 4xx
responses SHALL NOT be retried. Connection failures and connect timeouts
SHALL NOT be retried on the same URL; they go to the next fallback URL at
once, so a sleeping machine costs one connect timeout, not several.

#### Scenario: Rate limited then success
- **WHEN** a provider answers 429 once and then 200
- **THEN** the call returns the 200 response

#### Scenario: Client error not retried
- **WHEN** a provider answers 400
- **THEN** the call fails immediately with an error that includes the status and the provider name

#### Scenario: Model loading
- **WHEN** an LLM server answers 503 for 20 seconds while its model loads, then 200, with the default `retry_budget`
- **THEN** the call returns the 200 response

#### Scenario: Retries exhausted
- **WHEN** a provider with `retry_budget = 5` answers 503 on every attempt
- **THEN** the call fails after waits of 0.5, 1, and 2 seconds (the next 4-second wait would exceed 5 seconds) with an error that includes the last status

#### Scenario: Retry-After beyond the budget
- **WHEN** a provider with `retry_budget = 10` answers 429 with `Retry-After: 30`
- **THEN** the call fails at once with an error that includes status 429

### Requirement: Fallback URLs
When a provider's `base_url` cannot be connected to, the call SHALL try each
URL in `fallback_urls` in order. A response with an HTTP status SHALL NOT
trigger fallback; only connection failures and connect timeouts do. When
every URL fails to connect, the call SHALL fail with an error that lists
each URL tried.

#### Scenario: Primary down
- **WHEN** the primary URL refuses connections and the first fallback URL answers 200
- **THEN** the call returns the fallback's response

#### Scenario: Primary answers an error
- **WHEN** the primary URL answers 400
- **THEN** no fallback URL is tried

#### Scenario: All endpoints down
- **WHEN** the primary URL and every fallback URL refuse connections
- **THEN** the call fails with an error that lists every URL tried

### Requirement: Concurrency limit
At most `concurrency` requests SHALL be in flight per provider at a time.
Further requests SHALL wait.

#### Scenario: Limit respected
- **WHEN** a provider has `concurrency = 2` and 5 requests are started at once
- **THEN** no more than 2 are in flight at any time and all 5 complete

### Requirement: Authentication header
When a provider has an `api_key`, requests SHALL send it as
`Authorization: Bearer <key>`. The key SHALL NOT appear in error messages or
logs.

#### Scenario: Key not leaked in errors
- **WHEN** a request with an API key fails
- **THEN** the error message does not contain the key

### Requirement: Usage recording
Provider calls SHALL record usage per provider and per stage: input tokens,
output tokens, request count, and provider-specific units (for example
Firecrawl credits). When a price per unit is configured, the cost SHALL be
computed from it; otherwise the cost is zero and the usage is still
recorded.

#### Scenario: Usage summed
- **WHEN** two LLM calls report 100 and 50 input tokens
- **THEN** the recorded input tokens for that provider are 150

#### Scenario: No price configured
- **WHEN** a local provider has no price configured
- **THEN** its usage is recorded and its cost is 0

### Requirement: Cancellation
Cancelling the task that waits on a provider call SHALL cancel the HTTP
request and release its concurrency slot.

#### Scenario: Cancel in flight
- **WHEN** a call is cancelled while its request is in flight
- **THEN** the request is aborted and a waiting request can start

## MODIFIED Requirements

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

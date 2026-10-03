## MODIFIED Requirements

### Requirement: Profiles
The system SHALL load profiles from TOML files. Built-in profiles ship with
the package. User profiles are read from `$XDG_CONFIG_HOME/wosarcher/profiles/`
(`~/.config/wosarcher/profiles/` when `XDG_CONFIG_HOME` is unset). A user
profile with the same name as a built-in profile SHALL replace it. The
built-in profiles SHALL include `low-vram`, `workstation`, and `cloud`. The
built-in profiles that use local models (`low-vram` and `workstation`)
SHALL set `llm.timeout = 600` seconds, so prompt processing of a large
context on a small GPU, or a model load behind llama-swap, does not time
out before the first token. The built-in `cloud` profile, whose model is
a reasoning model, SHALL set `llm.reasoning_tokens = 4096`.

#### Scenario: Built-in profile
- **WHEN** no user profile named `cloud` exists and the user selects `cloud`
- **THEN** the built-in `cloud` profile is used

#### Scenario: User profile overrides built-in
- **WHEN** `~/.config/wosarcher/profiles/cloud.toml` exists and the user selects `cloud`
- **THEN** the user file is used and the built-in `cloud` profile is ignored

#### Scenario: Unknown profile
- **WHEN** the user selects a profile name that matches no file
- **THEN** the command fails with an error that names the profile and lists the available profiles

#### Scenario: Cloud reasoning allowance
- **WHEN** the user selects the built-in `cloud` profile
- **THEN** the resolved `llm.reasoning_tokens` is 4096

#### Scenario: Local LLM timeout
- **WHEN** the user selects the built-in `workstation` or `low-vram` profile
- **THEN** the resolved `llm.timeout` is 600

### Requirement: Provider block shape
Every model or service provider block (search, fetch, prefilter, score, llm)
SHALL accept the same fields: `provider`, `base_url`, `api_key`, `model`,
`device`, `release`, `fallback_urls`, `batch_size`, `concurrency`,
`connect_timeout`, `timeout`, `retry_budget` (seconds of waiting for
retries, default 60, not negative), and `prices` (optional per-unit prices
for cost recording). The `llm` block SHALL also accept `max_tokens_field`
(`max_completion_tokens`, the default, or `max_tokens`) and
`reasoning_tokens` (an integer, default 0, not negative, added to every
LLM request's output limit), and the `score`
block `rerank_scale` (`auto`, the default, `probability`, or `logit`).
Fields a provider does not use SHALL be ignored by it, not rejected.

#### Scenario: Remote endpoint
- **WHEN** a profile sets `score.base_url = "http://desktop.lan:8001"`
- **THEN** the resolved score provider uses that URL

#### Scenario: Invalid release value
- **WHEN** a profile sets `score.release = "unload"`
- **THEN** loading fails with an error that names the field and the allowed values `none`, `llama-swap`, `ollama`

#### Scenario: Invalid token field
- **WHEN** a profile sets `llm.max_tokens_field = "n_predict"`
- **THEN** loading fails with an error that names the field and the allowed values `max_completion_tokens`, `max_tokens`

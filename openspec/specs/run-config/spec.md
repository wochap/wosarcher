# run-config Specification

## Purpose

Resolves the configuration of a run from built-in defaults, a named profile,
environment variables, and per-command overrides, so providers can be
switched between local, LAN, and cloud endpoints without rebuilding anything.

## Requirements

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
A profile MAY set a top-level `description` string: one line that says
what the profile is for. It SHALL NOT be a configuration setting (it is not
part of the resolved configuration and cannot be set by environment or
`--set`). A `description` that is not a string SHALL fail with an error
that names the profile file. A profile without one has an empty
description. Each built-in profile SHALL have a description: `workstation`
"One GPU fits all models; models stay loaded.", `low-vram` "Models take
turns on one small GPU; slower, fits 8 GB.", and `cloud` "Hosted APIs
only; needs API keys.".

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

#### Scenario: Description is not a setting
- **WHEN** a user profile starts with `description = "SearXNG on homelab, models on desktop:gpu0."` and the user selects it
- **THEN** the configuration resolves without error and `wosarcher profile show` prints no `description` key

#### Scenario: Invalid description
- **WHEN** a user profile sets `description = 3`
- **THEN** resolving it fails with an error that names the profile file and `description`

### Requirement: Profile selection
The active profile SHALL be chosen in this order: the `--profile` option,
then the `WOSARCHER_PROFILE` environment variable, then the name stored by
`wosarcher profile use`, then the built-in default `workstation`.

#### Scenario: Option wins over environment
- **WHEN** `WOSARCHER_PROFILE=cloud` is set and the command runs with `--profile low-vram`
- **THEN** the `low-vram` profile is used

#### Scenario: Stored default
- **WHEN** the user has run `wosarcher profile use cloud` and neither `--profile` nor `WOSARCHER_PROFILE` is given
- **THEN** the `cloud` profile is used

#### Scenario: Profile use persists
- **WHEN** the user runs `wosarcher profile use low-vram`
- **THEN** later commands without `--profile` or `WOSARCHER_PROFILE` use `low-vram`

### Requirement: Precedence
Each setting SHALL be resolved with this precedence, lowest first: built-in
defaults, the active profile, environment variables, the server's global
settings (runs started by the server only), the run's depth preset, then
command-line or request overrides. Environment variables SHALL use the
prefix `WOSARCHER_` and `__` as the nesting separator (for example
`WOSARCHER_SCORE__PROVIDER=jev`).

#### Scenario: Environment overrides profile
- **WHEN** the profile sets `score.provider = "rerank"` and `WOSARCHER_SCORE__PROVIDER=jev` is set
- **THEN** the resolved `score.provider` is `jev`

#### Scenario: Override flag wins
- **WHEN** `WOSARCHER_SCORE__PROVIDER=jev` is set and the command runs with `--set score.provider=bm25`
- **THEN** the resolved `score.provider` is `bm25`

#### Scenario: Unset values fall back to defaults
- **WHEN** neither the profile, the environment, nor an override sets `chunk.size_chars`
- **THEN** the resolved `chunk.size_chars` is the built-in default 1800

#### Scenario: Preset between environment and overrides
- **WHEN** the profile sets `select.max_context_tokens = 12000`, the run uses depth `deep`, and the command adds `--set select.max_context_tokens=20000`
- **THEN** the resolved value is 20000, and it is 24000 without the `--set`

### Requirement: Field overrides
The CLI SHALL accept repeated `--set <dotted.key>=<value>` options that
override single fields. Values SHALL be converted to the field's type.

#### Scenario: Typed override
- **WHEN** the command runs with `--set score.top_k=12`
- **THEN** the resolved `score.top_k` is the integer 12

#### Scenario: Unknown key
- **WHEN** the command runs with `--set score.topk=12`
- **THEN** the command fails with an error that names the unknown key

### Requirement: Provider block shape
Every model or service provider block (search, fetch, prefilter, score, llm)
SHALL accept the same fields: `provider`, `base_url`, `api_key`, `model`,
`device`, `release`, `fallback_urls`, `batch_size`, `concurrency`,
`connect_timeout`, `timeout` (seconds to wait for a response, default 60;
default 300 in the `llm` block, sized for a small local model that
processes a long prompt before its first token), `retry_budget` (seconds
of waiting for retries, default 60, not negative), and `prices` (optional per-unit prices
for cost recording). The `llm` block SHALL also accept `max_tokens_field`
(`max_completion_tokens`, the default, or `max_tokens`),
`reasoning_tokens` (an integer, default 0, not negative, added to every
LLM request's output limit), and `max_continuations` (an integer, default
2, not negative: how many times the writer continues a report cut at the
output limit; 0 turns continuation off). The `score`
block SHALL also accept `rerank_scale` (`auto`, the default, `probability`,
or `logit`).
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

#### Scenario: Continuations
- **WHEN** no source sets `llm.max_continuations`
- **THEN** the resolved value is 2, and `--set llm.max_continuations=-1` fails with an error that names the field

#### Scenario: LLM timeout default
- **WHEN** no source sets `llm.timeout` or `search.timeout`
- **THEN** the resolved `llm.timeout` is 300 and `search.timeout` is 60

### Requirement: Validation
Configuration SHALL be validated when it is resolved. An invalid value SHALL
stop the command before any provider is called, with an error that names
the source (profile file, environment variable, or override) and the field.
`chunk.overlap` and `chunk.min_chars` SHALL each be below
`chunk.size_chars`. An unknown key, such as the removed `chunk.size`,
SHALL fail like any other invalid value.

#### Scenario: Invalid type in profile
- **WHEN** a profile file sets `chunk.size_chars = "large"`
- **THEN** the command fails and the error names the profile file and `chunk.size_chars`

#### Scenario: Floor above size
- **WHEN** an override sets `chunk.min_chars=2000` while `chunk.size_chars` is 1800
- **THEN** the command fails and the error names `chunk.min_chars`

#### Scenario: Old key
- **WHEN** a profile file sets `chunk.size = 1000`
- **THEN** the command fails and the error names the profile file and `chunk.size`

### Requirement: Secret redaction
Fields that hold secrets (every `api_key`, and any field marked secret)
SHALL never be printed, logged, or written to run artifacts in clear text.
They SHALL appear as `***` when set and as empty when unset.

#### Scenario: Show profile
- **WHEN** the user runs `wosarcher profile show cloud` and the profile has an API key
- **THEN** the output shows `api_key = "***"` for that provider

#### Scenario: Secret from environment
- **WHEN** `WOSARCHER_SCORE__API_KEY` is set
- **THEN** the resolved configuration uses the key, and its serialised form shows `***`

### Requirement: Profile commands
The CLI SHALL provide `wosarcher profile list` (one line per profile: a `*`
marking the active one, the name, the source built-in or user in
parentheses, and the description when it is not empty), `wosarcher profile
show [name]` (the fully resolved configuration with secrets redacted), and
`wosarcher profile use <name>`.

#### Scenario: List marks active profile
- **WHEN** the active profile is `cloud` and the user runs `wosarcher profile list`
- **THEN** the output lists every profile with its source and marks `cloud` as active

#### Scenario: List shows descriptions
- **WHEN** the user runs `wosarcher profile list` with only the built-in profiles
- **THEN** the `low-vram` line reads `  low-vram  (built-in)  Models take turns on one small GPU; slower, fits 8 GB.`

### Requirement: Output and context sizing
The `llm` block SHALL accept `max_output_tokens`, a positive integer,
default 8192 (a quarter of the default 32768-token `llm.context_window`).
It caps the writer's output limit.
`select.max_context_tokens` SHALL accept a positive integer or the string
`auto` (the default), which means no cap other than the room the context
window leaves. `fetch.max_pages` SHALL be a positive integer, default 40.

#### Scenario: Auto context in a profile
- **WHEN** a profile sets `select.max_context_tokens = "auto"` and `llm.context_window = 1000000`
- **THEN** the configuration resolves, and selection may use all the room the window leaves

#### Scenario: Auto by default
- **WHEN** no source sets `select.max_context_tokens`
- **THEN** the resolved value is `auto`

#### Scenario: Fixed cap
- **WHEN** a profile sets `select.max_context_tokens = 12000`
- **THEN** the resolved value is 12000

#### Scenario: Invalid context value
- **WHEN** a profile sets `select.max_context_tokens = "all"`
- **THEN** loading fails with an error naming the field

#### Scenario: Output cap default
- **WHEN** no source sets `llm.max_output_tokens`
- **THEN** the resolved value is 8192, and an exhaustive run's 3000-word target keeps its output limit of 6000 tokens

#### Scenario: Larger model sets its own cap
- **WHEN** a profile sets `llm.context_window = 1048576` and `llm.max_output_tokens = 131072`
- **THEN** the resolved values are 1048576 and 131072

#### Scenario: Page cap default
- **WHEN** no source sets `fetch.max_pages`
- **THEN** the resolved value is 40

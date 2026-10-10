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
out before the first token. Every built-in profile SHALL set
`llm.provider = "openai"` and no profile SHALL set a reasoning token
allowance.
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
- **THEN** the resolved `llm.provider` is `openai`, `llm.reasoning.plan`, `gap`, and `write` are `none`, and the resolved configuration has no `reasoning_tokens` key

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
`wosarcherd profile use`, then the built-in default `workstation`.

#### Scenario: Option wins over environment
- **WHEN** `WOSARCHER_PROFILE=cloud` is set and the command runs with `--profile low-vram`
- **THEN** the `low-vram` profile is used

#### Scenario: Stored default
- **WHEN** the service user has run `wosarcherd profile use cloud` and neither `--profile` nor `WOSARCHER_PROFILE` is given
- **THEN** the `cloud` profile is used

#### Scenario: Profile use persists
- **WHEN** the service user runs `wosarcherd profile use low-vram`
- **THEN** later engine commands without `--profile` or `WOSARCHER_PROFILE` use `low-vram`

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
for cost recording). The `llm` block's `provider` SHALL be `openai` (an
OpenAI-compatible chat endpoint); any other value SHALL fail resolution
naming `llm.provider` and `openai`. The `llm` block SHALL also accept
`max_tokens_field` (`max_completion_tokens`, the default, or `max_tokens`),
`reasoning` (a table with `plan`, `gap`, and `write`, each `none`, `low`,
`medium`, `high`, or `default`, default `none`; any other value fails
naming the key and the five values), and `max_continuations` (an integer,
default 2, not negative: how many times the writer continues a report cut
at the output limit; 0 turns continuation off). The `llm` block SHALL NOT
accept `reasoning_tokens`. The `score` block SHALL also accept
`rerank_scale` (`auto`, the default, `probability`, or `logit`).
Fields a provider does not use SHALL be ignored by it, not rejected.

#### Scenario: Remote endpoint
- **WHEN** a profile sets `score.base_url = "http://desktop.lan:8001"`
- **THEN** the resolved score provider uses that URL

#### Scenario: Invalid release value
- **WHEN** a profile sets `score.release = "unload"`
- **THEN** loading fails with an error that names the field and the allowed values `none`, `llama-swap`, `ollama`

#### Scenario: Invalid token field
- **WHEN** a profile sets `llm.max_tokens_field = "n_predict"`
- **THEN** loading fails with an error that names the field and the allowed values

#### Scenario: Continuations
- **WHEN** no source sets `llm.max_continuations`
- **THEN** the resolved value is 2, and `--set llm.max_continuations=-1` fails with an error that names the field

#### Scenario: LLM timeout default
- **WHEN** no source sets `llm.timeout` or `search.timeout`
- **THEN** the resolved `llm.timeout` is 300 and `search.timeout` is 60

#### Scenario: Thinking per step
- **WHEN** the command runs with `--set llm.reasoning.write=high`
- **THEN** the resolved `llm.reasoning.write` is `high` and `llm.reasoning.plan` and `gap` stay `none`

#### Scenario: Invalid thinking level
- **WHEN** a profile sets `llm.reasoning.gap = "max"`
- **THEN** loading fails naming `llm.reasoning.gap` and the values `none`, `low`, `medium`, `high`, `default`

#### Scenario: Old provider value
- **WHEN** a profile sets `llm.provider = "llm"`
- **THEN** resolution fails naming `llm.provider` and the value `openai`

#### Scenario: Removed allowance
- **WHEN** a profile sets `llm.reasoning_tokens = 4096`
- **THEN** loading fails naming the unknown field `reasoning_tokens`

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

### Requirement: Secret sources
Every secret setting `<x>` (`api_key` on the `search`, `fetch`, `prefilter`,
`score`, and `llm` blocks; `auth.password_hash`) SHALL accept two sibling
settings: `<x>_file`, a path to a file holding the value, and `<x>_command`,
a list of strings (a command and its arguments) whose standard output is
the value. Both SHALL be settable from a profile, the environment (as
`WOSARCHER_<BLOCK>__<X>_FILE` and `WOSARCHER_<BLOCK>__<X>_COMMAND`, the
command as a TOML list), and the CLI's `--set`. At most one of `<x>`,
`<x>_file`, and `<x>_command` SHALL be set after precedence is applied;
more than one SHALL fail resolution naming the setting and the three forms.

A file value SHALL be read when the configuration resolves, once per
process, with one trailing newline removed. A command SHALL run without a
shell, with its standard input closed and a 10-second timeout; it SHALL
exit with status 0, and its standard output with one trailing newline
removed is the value. An unreadable file, a command that cannot start,
exits non-zero, or times out, or a value that is not UTF-8 SHALL fail
resolution with an error that names the setting and the file path or the
command's first word, and never includes the file's or the command's
output. The failure SHALL happen before a run directory is created or a
provider is called.

A resolved value SHALL be a secret like a value given directly: redacted
as `***` in `profile show`, `request.json`, and every server response. The
file path and the command SHALL be shown as plain values. A fork or rerun
SHALL take secrets from the current process, as it does today, and SHALL
ignore `*_file` and `*_command` keys saved in the parent's configuration.

#### Scenario: Key from a file
- **WHEN** a profile sets `llm.api_key_file = "/run/secrets/llm"` and that file holds `sk-live\n`
- **THEN** the resolved `llm.api_key` is `sk-live`, `profile show` prints `api_key = "***"` and `api_key_file = "/run/secrets/llm"`, and the run's `request.json` shows the same

#### Scenario: Key from a command
- **WHEN** `WOSARCHER_SCORE__API_KEY_COMMAND='["pass", "show", "typesafe"]'` is set and that command prints `tk-1\n` and exits 0
- **THEN** the resolved `score.api_key` is `tk-1`

#### Scenario: Two forms set
- **WHEN** a profile sets `llm.api_key = "x"` and the command runs with `--set llm.api_key_file=/run/secrets/llm`
- **THEN** resolution fails with an error naming `llm.api_key` and the forms `api_key`, `api_key_file`, and `api_key_command`

#### Scenario: Missing file
- **WHEN** a profile sets `llm.api_key_file = "/run/secrets/missing"` and no such file exists
- **THEN** `wosarcher run` exits 2 with an error naming `llm.api_key_file` and `/run/secrets/missing`, and no run directory is created

#### Scenario: Failing command
- **WHEN** `score.api_key_command = ["false"]` is set
- **THEN** resolution fails with an error naming `score.api_key_command`, `false`, and the exit status, and the error contains no command output

#### Scenario: Password hash from a file
- **WHEN** `auth.password_hash_file` names a file holding a `scrypt$...` hash
- **THEN** the server requires that password, as if `auth.password_hash` held the hash

#### Scenario: Fork ignores a saved source
- **WHEN** a run's saved configuration has `llm.api_key = "***"` and `llm.api_key_file = "/run/secrets/old"`, and the current profile sets `llm.api_key = "sk-new"`
- **THEN** `wosarcher fork <id> --from write` resolves `llm.api_key` to `sk-new` without reading `/run/secrets/old`

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

### Requirement: Domain lists
The `search` block SHALL accept `allow_domains` and `block_domains`, each a
list of domain entries (default empty), and `filter_pages`, a positive
integer (default 3). Each entry SHALL be stored lowercase, with a leading
`*.` or `.` removed, so `*.GOB.pe`, `.gob.pe`, and `gob.pe` are the same
entry. An entry that is empty, contains a scheme, path, port, or
whitespace, or has no `.` SHALL fail validation with an error that names
the field and the entry. Duplicate entries SHALL be kept once, in first
order. A depth preset SHALL NOT set these keys.

#### Scenario: Entries normalised
- **WHEN** a profile sets `search.allow_domains = ["*.GOB.pe", "gob.pe", "sbs.gob.pe"]`
- **THEN** the resolved value is `["gob.pe", "sbs.gob.pe"]`

#### Scenario: URL rejected
- **WHEN** an override sets `search.block_domains=["https://facebook.com/"]`
- **THEN** resolving fails with an error that names `search.block_domains` and the entry

#### Scenario: Defaults
- **WHEN** no source sets the domain keys
- **THEN** both lists are empty and `search.filter_pages` is 3

#### Scenario: Preset cannot set domains
- **WHEN** a depth preset file sets `search.allow_domains`
- **THEN** loading the preset fails with an error that names the key

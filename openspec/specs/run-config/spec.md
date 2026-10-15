# run-config Specification

## Purpose

Resolves the configuration of a run from built-in defaults, a named profile,
environment variables, and per-command overrides, so providers can be
switched between local, LAN, and cloud endpoints without rebuilding anything.

## Requirements

### Requirement: Profiles
The system SHALL load profiles from TOML files in
`$XDG_CONFIG_HOME/wosarcher/profiles/` (`~/.config/wosarcher/profiles/`
when `XDG_CONFIG_HOME` is unset). The package SHALL ship no profile. A
profile names its provider entries (Requirement: Entry selection) and sets
only the keys of Requirement: Keys a profile may set.
A profile MAY set a top-level `description` string: one line that says
what the profile is for. It SHALL NOT be a configuration setting (it is not
part of the resolved configuration and cannot be set by environment or
`--set`). A `description` that is not a string SHALL fail with an error
that names the profile file. A profile without one has an empty
description.

#### Scenario: User profile
- **WHEN** `~/.config/wosarcher/profiles/cloud.toml` exists and the user selects `cloud`
- **THEN** that file is used

#### Scenario: Unknown profile
- **WHEN** the user selects a profile name that matches no file
- **THEN** the command fails with an error that names the profile and lists the available profiles

#### Scenario: Description is not a setting
- **WHEN** a user profile starts with `description = "SearXNG on homelab, models on desktop:gpu0."` and the user selects it
- **THEN** the configuration resolves without error and `wosarcher profile show` prints no `description` key

#### Scenario: Invalid description
- **WHEN** a user profile sets `description = 3`
- **THEN** resolving it fails with an error that names the profile file and `description`

#### Scenario: Built-in profile
- **WHEN** a fresh install has no file in `profiles/`
- **THEN** `wosarcher profile list` prints no profile, and `wosarcherd run "q"` fails naming the profiles directory

#### Scenario: User profile overrides built-in
- **WHEN** the user creates `profiles/workstation.toml`
- **THEN** it is an ordinary user profile; no built-in `workstation` exists to replace

#### Scenario: Cloud reasoning allowance
- **WHEN** a profile uses an llm entry whose chosen model sets no `reasoning`
- **THEN** the resolved `llm.reasoning.plan`, `gap`, and `write` are `none`, and the resolved configuration has no `reasoning_tokens` key

#### Scenario: Local LLM timeout
- **WHEN** an llm entry sets `timeout = 600`
- **THEN** a run using that entry resolves `llm.timeout` 600, and one using an entry without `timeout` resolves 300

### Requirement: Profile selection
The active profile SHALL be chosen in this order: the `--profile` option,
then the `WOSARCHER_PROFILE` environment variable, then the name stored by
`wosarcherd profile use`, then the first profile by name. With no profile
file at all, a command that resolves a configuration SHALL fail with an
error naming the profiles directory.

#### Scenario: Option wins over environment
- **WHEN** `WOSARCHER_PROFILE=cloud` is set and the command runs with `--profile low-vram`
- **THEN** the `low-vram` profile is used

#### Scenario: Stored default
- **WHEN** the service user has run `wosarcherd profile use cloud` and neither `--profile` nor `WOSARCHER_PROFILE` is given
- **THEN** the `cloud` profile is used

#### Scenario: Profile use persists
- **WHEN** the service user runs `wosarcherd profile use low-vram`
- **THEN** later engine commands without `--profile` or `WOSARCHER_PROFILE` use `low-vram`

#### Scenario: First profile by name
- **WHEN** the profiles are `cloud` and `default`, and nothing selects or stores a profile
- **THEN** the `cloud` profile is used and `profile list` marks it active

#### Scenario: No profiles
- **WHEN** the profiles directory is empty and the user runs `wosarcherd run "q"`
- **THEN** the command exits 2 with an error naming the profiles directory

### Requirement: Precedence
Each setting SHALL be resolved with this precedence, lowest first: built-in
defaults, the chosen provider entries (each block replaced whole by its
entry), the chosen model's values from its entry's `models` table, the
chosen model's values from the active profile's `models` table, the
active profile, environment variables, the server's global settings (runs
started by the server only), the run's depth preset, then command-line or
request overrides. The chosen model SHALL be the run's `llm.model`
override, else the profile's `llm.model`, else the entry's `model`.
Environment variables SHALL use the prefix `WOSARCHER_` and `__` as the
nesting separator (for example `WOSARCHER_SELECT__MAX_CONTEXT_TOKENS=auto`).

#### Scenario: Profile over entry
- **WHEN** the `omniroute` entry has `model = "research-smart"` and the profile sets `llm.model = "research-fast"`
- **THEN** the resolved `llm.model` is `research-fast` and the model values come from `models.research-fast`

#### Scenario: Profile model table over entry model table
- **WHEN** the entry lists `models.research-smart` with `max_output_tokens = 131072` and `reasoning = { write = "low" }`, and the profile's `models.research-smart` sets `reasoning = { write = "high" }`
- **THEN** a run with model `research-smart` resolves `llm.reasoning.write` `high` and `llm.max_output_tokens` 131072

#### Scenario: Profile model table for another model
- **WHEN** the profile's `models` table lists only `research-smart` and a run uses `--model research-fast`
- **THEN** the model values come from the entry's `models.research-fast` (or the built-in defaults), not from the profile

#### Scenario: Run edit over profile model table
- **WHEN** the profile's `models.research-smart` sets `context_window = 200000` and the run request's `llm` sets `context_window = 100000`
- **THEN** the resolved `llm.context_window` is 100000

#### Scenario: Environment overrides profile
- **WHEN** the profile sets `select.max_context_tokens = 12000` and `WOSARCHER_SELECT__MAX_CONTEXT_TOKENS=auto` is set
- **THEN** the resolved `select.max_context_tokens` is `auto`

#### Scenario: Override flag wins
- **WHEN** the score entry sets `min_score = 2.0` and the command runs with `--set score.min_score=1.0`
- **THEN** the resolved `score.min_score` is 1.0

#### Scenario: Unset values fall back to defaults
- **WHEN** neither an entry, the profile, the environment, nor an override sets `chunk.size_chars`
- **THEN** the resolved `chunk.size_chars` is the built-in default 1800

#### Scenario: Model override picks model values
- **WHEN** the entry lists `models.a` with `context_window = 1000000` and `models.b` with `context_window = 131072`, its default model is `a`, and the command runs with `--model b`
- **THEN** the resolved `llm.context_window` is 131072

#### Scenario: Preset between environment and overrides
- **WHEN** the run uses depth `deep` and the command adds `--set fetch.max_pages=80`
- **THEN** the resolved `fetch.max_pages` is 80, and it is 60 without the `--set`

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
`rerank_scale` (`auto`, the default, `probability`, or `logit`) and
`candidates` (a positive integer, default 50: how many pairs per query the
prefilter passes to the scorer). The `prefilter` block SHALL NOT accept
`top_k`.
Fields a provider does not use SHALL be ignored by it, not rejected.

#### Scenario: Remote endpoint
- **WHEN** a score entry sets `base_url = "http://desktop.lan:8001"`
- **THEN** the resolved score provider uses that URL

#### Scenario: Invalid release value
- **WHEN** a score entry sets `release = "unload"`
- **THEN** loading fails with an error that names the field and the allowed values `none`, `llama-swap`, `ollama`

#### Scenario: Invalid token field
- **WHEN** an llm entry sets `max_tokens_field = "n_predict"`
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
- **WHEN** an llm entry's `models.m` sets `reasoning = { gap = "max" }`
- **THEN** loading fails naming `reasoning.gap` and the values `none`, `low`, `medium`, `high`, `default`

#### Scenario: Old provider value
- **WHEN** an llm entry sets `provider = "llm"`
- **THEN** resolution fails naming `llm.provider` and the value `openai`

#### Scenario: Removed allowance
- **WHEN** an llm entry sets `reasoning_tokens = 4096`
- **THEN** loading fails naming the unknown field `reasoning_tokens`

#### Scenario: Candidates default
- **WHEN** no source sets `score.candidates`
- **THEN** the resolved value is 50

#### Scenario: Old prefilter key
- **WHEN** a prefilter entry sets `top_k = 100`
- **THEN** loading fails naming the entry file and `top_k`

### Requirement: Validation
Configuration SHALL be validated when it is resolved. An invalid value SHALL
stop the command before any provider is called, with an error that names
the source (entry file, profile file, environment variable, depth preset
file, or override) and the field. A value from an entry's `models` table
SHALL name the entry file and the model. `chunk.overlap` and
`chunk.min_chars` SHALL each be below `chunk.size_chars`. An unknown key,
such as the removed `chunk.size`, SHALL fail like any other invalid value.

#### Scenario: Invalid type in profile
- **WHEN** a profile file sets `chunk.size_chars = "large"`
- **THEN** the command fails and the error names the profile file and `chunk.size_chars`

#### Scenario: Invalid type in an entry
- **WHEN** the entry `providers/fetch/firecrawl.toml` sets `max_chars = "lots"`
- **THEN** the command fails and the error names that file and `fetch.max_chars`

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
- **WHEN** the user runs `wosarcher profile show cloud` and an entry it uses has an API key
- **THEN** the output shows `api_key = "***"` for that provider

#### Scenario: Secret from an override
- **WHEN** the command runs with `--set score.api_key=tk-1`
- **THEN** the resolved configuration uses the key, and its serialised form shows `***`

#### Scenario: Secret from environment
- **WHEN** `WOSARCHER_AUTH__PASSWORD_HASH` is set
- **THEN** the resolved configuration uses the hash, and its serialised form shows `***`

### Requirement: Secret sources
Every secret setting `<x>` (`api_key` on the `search`, `fetch`, `prefilter`,
`score`, and `llm` blocks; `auth.password_hash`) SHALL accept two sibling
settings: `<x>_file`, a path to a file holding the value, and `<x>_command`,
a list of strings (a command and its arguments) whose standard output is
the value. The provider-block forms SHALL be settable from a provider entry
and the CLI's `--set`; `auth.password_hash` and its forms SHALL be settable
from the environment (as `WOSARCHER_AUTH__PASSWORD_HASH_FILE` and
`WOSARCHER_AUTH__PASSWORD_HASH_COMMAND`, the command as a TOML list) and
`--set`. At most one of `<x>`, `<x>_file`, and `<x>_command` SHALL be set
after precedence is applied; more than one SHALL fail resolution naming
the setting and the three forms.

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
file path and the command SHALL be shown as plain values in `profile show`
and `request.json`. A fork SHALL take secrets from the current entries the
parent used (run-store "Fork") and SHALL ignore `*_file` and `*_command`
keys saved in the parent's configuration.

#### Scenario: Key from a file
- **WHEN** an llm entry sets `api_key_file = "/run/secrets/llm"` and that file holds `sk-live\n`
- **THEN** the resolved `llm.api_key` is `sk-live`, `profile show` prints `api_key = "***"` and `api_key_file = "/run/secrets/llm"`, and the run's `request.json` shows the same

#### Scenario: Key from a command
- **WHEN** a score entry sets `api_key_command = ["pass", "show", "typesafe"]` and that command prints `tk-1\n` and exits 0
- **THEN** the resolved `score.api_key` is `tk-1`

#### Scenario: Two forms set
- **WHEN** an llm entry sets `api_key = "x"` and the command runs with `--set llm.api_key_file=/run/secrets/llm`
- **THEN** resolution fails with an error naming `llm.api_key` and the forms `api_key`, `api_key_file`, and `api_key_command`

#### Scenario: Missing file
- **WHEN** an llm entry sets `api_key_file = "/run/secrets/missing"` and no such file exists
- **THEN** `wosarcher run` exits 2 with an error naming `llm.api_key_file` and `/run/secrets/missing`, and no run directory is created

#### Scenario: Failing command
- **WHEN** `score.api_key_command = ["false"]` is set
- **THEN** resolution fails with an error naming `score.api_key_command`, `false`, and the exit status, and the error contains no command output

#### Scenario: Password hash from a file
- **WHEN** `auth.password_hash_file` names a file holding a `scrypt$...` hash
- **THEN** the server requires that password, as if `auth.password_hash` held the hash

#### Scenario: Fork ignores a saved source
- **WHEN** a run's saved configuration has `llm.api_key = "***"` and `llm.api_key_file = "/run/secrets/old"`, and the llm entry it used now sets `api_key = "sk-new"`
- **THEN** `wosarcher fork <id> --from write` resolves `llm.api_key` to `sk-new` without reading `/run/secrets/old`

### Requirement: Profile commands
The CLI SHALL provide `wosarcher profile list` (one line per profile: a `*`
marking the active one, the name, the source `user` in parentheses, the
entries it uses as `search · fetch · prefilter · score · llm`, and the
description when it is not empty), `wosarcher profile show [name]` (the
entries it uses, then the profile's own values, including each
`models.<id>` value as `models.<id>.<key> = <value>`, then the fully
resolved configuration with secrets redacted), and `wosarcher profile use
<name>`.

#### Scenario: List marks active profile
- **WHEN** the active profile is `cloud` and the user runs `wosarcher profile list`
- **THEN** the output lists every profile with its source and marks `cloud` as active

#### Scenario: List shows entries and descriptions
- **WHEN** the profile `default` uses `searxng`, `firecrawl`, `embeddings`, `jev-strict`, and `omniroute`, with the description "Home lab."
- **THEN** its line reads `  default  (user)  searxng · firecrawl · embeddings · jev-strict · omniroute  Home lab.`

#### Scenario: Show lists entries first
- **WHEN** the user runs `wosarcher profile show default`
- **THEN** the output starts with the five `use` lines, then the profile's own keys, then the resolved configuration

#### Scenario: Show prints the model table
- **WHEN** the profile `cloud-rerank` sets `models."claude-sonnet-5-5".reasoning.write = "high"` and the user runs `wosarcher profile show cloud-rerank`
- **THEN** its own values include the line `models.claude-sonnet-5-5.reasoning.write = "high"`

#### Scenario: List shows descriptions
- **WHEN** the user runs `wosarcher profile list` and the profile `low-vram` describes itself as "Models take turns on one small GPU; slower, fits 8 GB."
- **THEN** the `low-vram` line ends with that description

### Requirement: Output and context sizing
The `llm` block SHALL accept `max_output_tokens`, a positive integer,
default 8192 (a quarter of the default 32768-token `llm.context_window`).
It caps the writer's output limit. Both come from the chosen model's
entry values when the entry lists the model (provider-entries "LLM entries
and models"), and a run MAY override them.
`select.max_context_tokens` SHALL accept a positive integer or the string
`auto` (the default), which means no cap other than the room the context
window leaves. `fetch.max_pages` SHALL be a positive integer, default 40.

#### Scenario: Auto context in a profile
- **WHEN** a profile sets `select.max_context_tokens = "auto"` and the chosen model's `context_window` is 1000000
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
- **WHEN** the chosen model is not listed and nothing overrides `llm.max_output_tokens`
- **THEN** the resolved value is 8192, and an exhaustive run's 3000-word target keeps its output limit of 6000 tokens

#### Scenario: Larger model sets its own cap
- **WHEN** the chosen model's entry values set `context_window = 1048576` and `max_output_tokens = 131072`
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

### Requirement: Entry selection
A profile SHALL name its entries in a `[use]` table with the keys `search`,
`fetch`, `prefilter`, `score`, and `llm` (provider-entries "Entry files").
For each block the entry SHALL be chosen in this order: the run's own
choice (`--use BLOCK=NAME` or the request's `use`), then
`WOSARCHER_USE__<BLOCK>`, then the profile's `[use]`. A block with exactly
one entry (built-in entries count) MAY be left out and SHALL use that
entry. A block with several entries and no choice SHALL fail resolution
naming the block and its entries. A choice that names no entry of its block
SHALL fail naming the block, the name, and the block's entries, before a
run directory is created or a provider is called. `--use` SHALL be
repeatable, take `BLOCK=NAME`, and fail on an unknown block naming the five
blocks.

#### Scenario: Profile choice
- **WHEN** the profile `default` has `[use]` with `score = "rerank"` and `llm = "omniroute"`, and a run names no entries
- **THEN** the run's `score` block is the `rerank` entry and its `llm` block is the `omniroute` entry

#### Scenario: Run choice wins
- **WHEN** the profile uses `score = "rerank"`, `WOSARCHER_USE__SCORE=bm25` is set, and the command runs with `--use score=jev-strict`
- **THEN** the run's `score` block is the `jev-strict` entry

#### Scenario: Single entry implied
- **WHEN** `providers/search/` holds only `searxng.toml` and the profile's `[use]` has no `search`
- **THEN** the run uses the `searxng` entry

#### Scenario: Ambiguous block
- **WHEN** the score entries are `rerank` and the built-in `bm25`, and neither the profile nor the run names a score entry
- **THEN** resolution fails naming `score`, `bm25`, and `rerank`

#### Scenario: Unknown entry
- **WHEN** the command runs with `--use llm=sonet`
- **THEN** the command fails naming `llm`, `sonet`, and the llm entries, and no run directory is created

### Requirement: Keys a profile may set
A profile SHALL set only `description`, `[use]`, `llm.model`,
`search.allow_domains`, `search.block_domains`, `search.language`,
`search.time_range`, `search.filter_pages`, a `models` table, and keys
outside the five provider blocks. The `models` table SHALL be keyed by
model ID and each model SHALL set only the keys an llm entry's model may
set (provider-entries "LLM entries and models": `context_window`,
`max_output_tokens`, `reasoning`, `gap_context_tokens`), validated the same
way; any other key SHALL fail naming the profile file, the model, and the
key. A profile SHALL NOT set the keys a depth preset owns (depth-presets
"Allowed preset keys") or the keys a model owns at their own place
(`llm.context_window`, `llm.max_output_tokens`, `llm.reasoning.*`,
`research.gap_context_tokens`); a profile sets those only through
`models.<id>`. Any other key SHALL fail when the profile loads, naming the
profile file, the key, and its owner (entry, depth, or model). Environment
variables SHALL follow the same rule (they cannot set a `models` table),
and `WOSARCHER_USE__<BLOCK>` SHALL be allowed. `--set` and a request's
`set` SHALL stay able to set any key.

#### Scenario: Provider key in a profile
- **WHEN** a profile sets `score.base_url = "http://desktop.lan:8001/v1"`
- **THEN** loading fails naming the profile file, `score.base_url`, and that provider entries own it

#### Scenario: Model key in a profile
- **WHEN** a profile sets `llm.reasoning.write = "high"`
- **THEN** loading fails naming the profile file, `llm.reasoning.write`, and that the model owns it

#### Scenario: Model table in a profile
- **WHEN** a profile sets `models."claude-sonnet-5-5" = { context_window = 200000, reasoning = { write = "high" } }`
- **THEN** the profile loads without error

#### Scenario: Unknown key in a profile model table
- **WHEN** a profile's `models.research-smart` sets `timeout = 900`
- **THEN** loading fails naming the profile file, `research-smart`, and `timeout`

#### Scenario: Environment cannot set a block key
- **WHEN** `WOSARCHER_SCORE__PROVIDER=jev` is set
- **THEN** resolution fails naming `WOSARCHER_SCORE__PROVIDER` and that provider entries own `score.provider`

#### Scenario: Set reaches any key
- **WHEN** the command runs with `--set score.min_score=1.5`
- **THEN** the resolved `score.min_score` is 1.5

### Requirement: Catalog block
The configuration SHALL have a `catalog` block with:
- `max_depth` (1 to 10, default 3), `max_nodes` (1 to 5000, default 200),
  `pages_per_node` (1 to 10, default 2), and `expand` (`links`, `search`,
  or `both`, default `both`): the defaults a structure's limits and expand
  mode take when it leaves them unset;
- `max_children` (a positive integer, default 50): children kept per
  extraction;
- `concurrency` (a positive integer, default 4): extraction calls in
  flight;
- `context_tokens` (a positive integer or `auto`, default `auto`): the
  extract budget (catalog-extraction "Extract stage").

The block SHALL be validated like any other (Requirement: Validation). A
profile MAY set these keys (they are outside the five provider blocks); a
depth preset SHALL NOT set them (depth-presets "Allowed preset keys"). A
run request's structure limits and expand mode SHALL win over the block.

#### Scenario: Defaults
- **WHEN** no source sets the `catalog` block
- **THEN** the resolved values are `max_depth` 3, `max_nodes` 200, `pages_per_node` 2, `expand` `both`, `max_children` 50, `concurrency` 4, and `context_tokens` `auto`

#### Scenario: Invalid value
- **WHEN** a profile sets `catalog.concurrency = 0`
- **THEN** loading fails with an error naming the profile file and `catalog.concurrency`

#### Scenario: Preset cannot set catalog keys
- **WHEN** a depth preset file sets `catalog.max_nodes`
- **THEN** loading the preset fails naming the file and the key

#### Scenario: Structure wins
- **WHEN** a profile sets `catalog.max_nodes = 500` and the run's structure sets `max_nodes` 200
- **THEN** the run stops adding nodes at 200

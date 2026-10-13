# provider-entries Specification

## Purpose

Named provider entries per block (search, fetch, prefilter, score, llm), so
a profile or a run picks each block's provider by name instead of copying
whole provider blocks into every profile.

## Requirements

### Requirement: Entry files
The system SHALL load provider entries from
`$XDG_CONFIG_HOME/wosarcher/providers/<block>/<name>.toml`
(`~/.config/wosarcher/providers/...` when `XDG_CONFIG_HOME` is unset),
where `<block>` is one of `search`, `fetch`, `prefilter`, `score`, and
`llm`, and `<name>` is any name the user picks. The directory SHALL decide
the entry's block; the file SHALL hold that block's fields at the top level
(no `[block]` table) and MAY start with a one-line `description` string,
which is not a setting. A directory under `providers/` that is not a block
name SHALL fail resolution naming the directory and the five blocks. An
entry SHALL be validated as its block when it is used, and an invalid
value SHALL fail with an error naming the entry file and the field.

#### Scenario: Scorer entry
- **WHEN** `providers/score/jev-strict.toml` sets `provider = "jev"`, `base_url`, `api_key_file`, and `min_score = 2.0`, and a run uses `score = "jev-strict"`
- **THEN** the run's resolved `score` block is that entry with every other score field at its default

#### Scenario: Same provider in two blocks
- **WHEN** `providers/prefilter/kw.toml` and `providers/score/kw.toml` both set `provider = "bm25"`
- **THEN** `kw` is offered as a prefilter entry and as a score entry, each in its own block

#### Scenario: Unknown block directory
- **WHEN** `providers/scorer/x.toml` exists
- **THEN** resolution fails naming `providers/scorer` and the blocks `search`, `fetch`, `prefilter`, `score`, `llm`

#### Scenario: Invalid entry value
- **WHEN** `providers/score/rr.toml` sets `release = "unload"` and a run uses it
- **THEN** resolution fails naming the file `providers/score/rr.toml` and `release`

### Requirement: Built-in entries
The system SHALL provide entries that need no file: prefilter `bm25`
(keyword ranking), prefilter `none` (every pair reaches the scorer), and
score `bm25`. A user entry file with the same block and name SHALL replace
the built-in entry. Built-in entries SHALL be listed with source
`builtin`, user entries with source `user`.

#### Scenario: Built-in without files
- **WHEN** the `providers/` directory is empty
- **THEN** the prefilter entries are `bm25` and `none` and the score entry is `bm25`, each with source `builtin`

#### Scenario: User file replaces built-in
- **WHEN** `providers/score/bm25.toml` sets `provider = "bm25"` and `candidates = 80`
- **THEN** the score entry `bm25` has source `user` and a run using it scores 80 candidates per query

### Requirement: Keys an entry may set
An entry SHALL NOT set a key owned by a depth preset (`search.max_results`,
`fetch.max_pages`, `score.top_k`), by the profile (`search.allow_domains`,
`search.block_domains`, `search.language`, `search.time_range`,
`search.filter_pages`), or by a model (`context_window`,
`max_output_tokens`, `reasoning` at the top of an `llm` entry). Such a key
SHALL fail when the entry loads, naming the entry file, the key, and its
owner. Every other field of the block SHALL be allowed, including secrets
as `api_key`, `api_key_file`, or `api_key_command` (run-config "Secret
sources"). An `llm` entry's `model` SHALL be its default model.

#### Scenario: Depth key in an entry
- **WHEN** `providers/score/jev-wide.toml` sets `top_k = 25`
- **THEN** loading fails naming the file, `top_k`, and that depth presets own it

#### Scenario: Domain list in an entry
- **WHEN** `providers/search/searxng.toml` sets `block_domains = ["facebook.com"]`
- **THEN** loading fails naming the file, `block_domains`, and that profiles own it

#### Scenario: Secret from a file
- **WHEN** `providers/llm/omniroute.toml` sets `api_key_file = "/run/secrets/omniroute"`
- **THEN** a run using `omniroute` reads its key from that file and records `api_key = "***"`

### Requirement: LLM entries and models
An `llm` entry SHALL be an OpenAI-compatible endpoint (`provider =
"openai"`) with a default `model`. It MAY have a `models` table keyed by
model ID; each model MAY set only `context_window` (positive integer),
`max_output_tokens` (positive integer), `reasoning` (a table with `plan`,
`gap`, and `write`, each `none`, `low`, `medium`, `high`, or `default`),
and `gap_context_tokens` (a positive integer or `auto`). Any other key
SHALL fail naming the entry file and the model. When a run's model is
listed, these values SHALL apply as the model layer of run-config
"Precedence" (`llm.context_window`, `llm.max_output_tokens`,
`llm.reasoning.*`, `research.gap_context_tokens`). When it is not listed,
the built-in defaults SHALL apply: `context_window` 32768,
`max_output_tokens` 8192, every reasoning step `none`, and
`gap_context_tokens` 4000.

#### Scenario: Listed model
- **WHEN** the entry `omniroute` has `model = "research-smart"` and `models.research-smart = { context_window = 1048576, max_output_tokens = 131072, gap_context_tokens = "auto", reasoning = { write = "low" } }`, and a run uses `llm = "omniroute"` with no model override
- **THEN** the run resolves `llm.model` `research-smart`, `llm.context_window` 1048576, `llm.max_output_tokens` 131072, `research.gap_context_tokens` `auto`, and `llm.reasoning.write` `low`

#### Scenario: Unlisted model
- **WHEN** a run uses `llm = "omniroute"` with `llm.model = "qwen3-30b-a3b"`, which `models` does not list
- **THEN** the run resolves `llm.context_window` 32768, `llm.max_output_tokens` 8192, every reasoning step `none`, and `research.gap_context_tokens` 4000

#### Scenario: Run overrides a model limit
- **WHEN** a run uses the unlisted model `qwen3-30b-a3b` and sets `llm.context_window` 262144
- **THEN** the resolved `llm.context_window` is 262144 and `llm.max_output_tokens` stays 8192

#### Scenario: Unknown model key
- **WHEN** `models.research-smart` sets `timeout = 900`
- **THEN** loading fails naming the entry file, `research-smart`, and `timeout`

### Requirement: Providers list command
`wosarcher providers list [--block BLOCK] [--json]` SHALL print, through the
daemon, every entry grouped by block in the order search, fetch, prefilter,
score, llm: one line per entry with its name, its source in parentheses,
its adapter (`provider`), and its description when not empty. For an `llm`
entry, an indented line per listed model SHALL follow, with the default
model marked `(default)` and its context window and output limit. `--block`
SHALL limit the list to one block; an unknown block SHALL exit 2 naming the
five blocks. `--json` SHALL print the `GET /api/providers` answer.

#### Scenario: List
- **WHEN** the daemon has the score entries `rerank`, `jev-strict`, and the built-in `bm25`, and the user runs `wosarcher providers list --block score`
- **THEN** three lines are printed: `bm25  (built-in)  bm25`, `jev-strict  (user)  jev`, and `rerank  (user)  rerank`

#### Scenario: Unknown block
- **WHEN** the user runs `wosarcher providers list --block scorer`
- **THEN** the command exits 2 naming `search`, `fetch`, `prefilter`, `score`, `llm`

### Requirement: Providers route
`GET /api/providers` SHALL return a list of entries in block order, then by
name. Each entry SHALL have:
- `block` and `name`;
- `source` (`builtin` or `user`) and `description`;
- `provider`, `url` (the `base_url`), `model` (the default model, empty
  when none), `device`, and `release`;
- for an `llm` entry, `models`: one item per listed model with `id`,
  `context_window`, `max_output_tokens`, `reasoning`, and
  `gap_context_tokens`, the default model first;
- the stored health of that entry (http-api "Provider health").

An entry that fails to load SHALL still be listed with its block, name,
source, and an `error` string, and SHALL NOT fail the route. No secret, no
`*_file` path, and no `*_command` list SHALL appear in the answer.

#### Scenario: LLM entry models
- **WHEN** the entry `agents` has default model `qwen3-14b` with limits 32768 / 8192 and also lists `gemma-3-12b` without limits
- **THEN** the `agents` item has `models` `[{"id": "qwen3-14b", "context_window": 32768, "max_output_tokens": 8192, ...}, {"id": "gemma-3-12b", "context_window": null, "max_output_tokens": null, ...}]`

#### Scenario: Broken entry listed
- **WHEN** `providers/score/old.toml` sets `top_k = 25`
- **THEN** `GET /api/providers` answers 200 and the `old` item has an `error` naming `top_k`

#### Scenario: No secrets
- **WHEN** an entry sets `api_key_file`
- **THEN** the answer contains neither the key nor the file path

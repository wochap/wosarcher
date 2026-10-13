# depth-presets Specification

## Purpose

Named research depths (quick to exhaustive) that set how broad a run's
search, fetch, scoring, context, and report length are. They are chosen per
run, independently of the provider profile.

## Requirements

### Requirement: Built-in presets
The package SHALL ship the depth presets `quick`, `standard`, `deep`, and
`exhaustive` as TOML files. Each has a one-line `description`:

- `quick`: "Fast overview: few searches, short report."
- `standard`: "Balanced: today's default."
- `deep`: "Several research rounds that follow up on gaps."
- `exhaustive`: "Many rounds and sources; slow, for thorough reports."

The presets SHALL set these values:

| key | quick | standard | deep | exhaustive |
|---|---|---|---|---|
| `plan.max_sub_queries` | 3 | - | 6 | 10 |
| `search.max_results` | 5 | - | 10 | 10 |
| `fetch.max_pages` | 15 | - | 60 | 100 |
| `score.top_k` | 6 | - | 10 | 8 |
| `write.words` | 600 | - | 2000 | 3000 |
| `research.rounds` | - | - | 3 | 5 |
| `research.queries_per_round` | - | - | 3 | 4 |

`standard` SHALL set no key, so a `standard` run resolves like a run with no
depth. Context budgets are not depth keys: the writer's context is bounded
by the passages that scoring keeps, by the profile's or the run's
`select.max_context_tokens`, and by the room the chosen model's
`llm.context_window` leaves.

#### Scenario: Standard equals defaults
- **WHEN** a run uses depth `standard` with no other override
- **THEN** its resolved configuration equals that of the same run with no depth

#### Scenario: Deep values
- **WHEN** a run uses depth `deep`
- **THEN** the resolved `plan.max_sub_queries` is 6, `fetch.max_pages` is 60, `write.words` is 2000, `research.rounds` is 3, and `select.max_context_tokens` keeps the profile's value

### Requirement: Allowed preset keys
A preset SHALL only set `plan.max_sub_queries`, `search.max_results`,
`fetch.max_pages`, `score.top_k`, `write.words`, `research.rounds`, and
`research.queries_per_round`, plus `description`. These are the depth keys:
no provider entry or profile may set them (run-config "Keys a profile may
set", provider-entries "Keys an entry may set"). Any other key, such as a
provider field, `select.max_context_tokens`, or
`research.gap_context_tokens`, SHALL fail when the preset is loaded, with
an error that names the preset file and the key. A preset value SHALL be
validated like any other setting.

#### Scenario: Provider key rejected
- **WHEN** a preset file sets `llm.model`
- **THEN** loading fails with an error naming the file and `llm.model`

#### Scenario: Context budget rejected
- **WHEN** a user preset sets `select.max_context_tokens = 20000`
- **THEN** loading fails with an error naming the file and `select.max_context_tokens`

### Requirement: Preset expansion
A depth SHALL be applied as a configuration layer above the environment and
below every override of the run (`--set`, writing flags, research flags, and
request fields). Errors in its values SHALL name the preset file. So a preset wins over the defaults, the entries, the profile, the
environment, and the server's global settings, and loses to anything the
user sets for the run. An unknown depth name SHALL fail before any provider
is called, with an error that lists the known presets, built-in and user.
The depth `custom` SHALL apply no preset.

#### Scenario: Flag beats preset
- **WHEN** the user runs with depth `deep` and `--words 800`
- **THEN** the resolved `write.words` is 800 and `plan.max_sub_queries` is 6

#### Scenario: Preset beats default
- **WHEN** no source sets `plan.max_sub_queries` and the run uses depth `quick`
- **THEN** the resolved `plan.max_sub_queries` is 3

#### Scenario: Unknown depth
- **WHEN** the user runs with depth `huge` and the user preset `wide` exists
- **THEN** the command fails with an error listing `quick`, `standard`, `deep`, `exhaustive`, `wide`

#### Scenario: Preset beats environment
- **WHEN** `WOSARCHER_PLAN__MAX_SUB_QUERIES=4` is set and the run uses depth `quick`
- **THEN** resolution fails naming `WOSARCHER_PLAN__MAX_SUB_QUERIES` and that depth presets own `plan.max_sub_queries`; only the preset or the run sets it

### Requirement: Depth commands
The CLI SHALL provide `wosarcher depth list` (one line per preset: the name,
its source `(user)` for a user preset, and its description) and
`wosarcher depth show NAME` (the keys the preset sets with their values, or
"sets nothing; uses the defaults" for `standard`). An unknown name SHALL
fail with exit status 2 and the list of known presets.

#### Scenario: List
- **WHEN** the user runs `wosarcher depth list` with no user preset
- **THEN** four lines show `quick`, `standard`, `deep`, and `exhaustive` with their descriptions

#### Scenario: Show
- **WHEN** the user runs `wosarcher depth show quick`
- **THEN** the output lists `plan.max_sub_queries = 3` through `write.words = 600`

### Requirement: User presets
The system SHALL also load depth presets from
`$XDG_CONFIG_HOME/wosarcher/depths/<name>.toml`
(`~/.config/wosarcher/depths/` when `XDG_CONFIG_HOME` is unset), with the
same file shape and the same allowed keys as the built-in presets. They
SHALL be listed after the built-in presets, by name, with source `user`;
built-in presets have source `builtin`. A user preset named like a
built-in preset or `custom` SHALL fail when the presets are listed, naming
the file. A run MAY use a user preset by name wherever it may use a
built-in one.

#### Scenario: User preset listed
- **WHEN** `depths/wide.toml` sets `description = "Broad survey."`, `plan.max_sub_queries = 10`, and `score.top_k = 25`
- **THEN** `wosarcher depth list` shows `quick`, `standard`, `deep`, `exhaustive`, then `wide` with "(user)" and its description

#### Scenario: Run with a user preset
- **WHEN** the user runs `wosarcher run "q" --depth wide`
- **THEN** the resolved `plan.max_sub_queries` is 10 and `score.top_k` is 25

#### Scenario: Built-in name taken
- **WHEN** `depths/deep.toml` exists in the user directory
- **THEN** listing the presets fails naming that file and `deep`

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
depth. No preset SHALL set `select.max_context_tokens`, so every preset uses
the default `auto`: the writer's context is bounded by the passages that
scoring keeps and by the room `llm.context_window` leaves.

#### Scenario: Standard equals defaults
- **WHEN** a run uses depth `standard` with no other override
- **THEN** its resolved configuration equals that of the same run with no depth

#### Scenario: Deep values
- **WHEN** a run uses depth `deep`
- **THEN** the resolved `plan.max_sub_queries` is 6, `fetch.max_pages` is 60, `write.words` is 2000, `research.rounds` is 3, and `select.max_context_tokens` is `auto`

### Requirement: Allowed preset keys
A preset SHALL only set the keys listed in Requirement: Built-in presets,
plus `description`. Any other key, such as a provider field or
`research.gap_context_tokens`, SHALL fail when the preset is loaded, with
an error that names the preset file and the key. A preset value SHALL be
validated like any other setting.

#### Scenario: Provider key rejected
- **WHEN** a preset file sets `llm.model`
- **THEN** loading fails with an error naming the file and `llm.model`

### Requirement: Preset expansion
A depth SHALL be applied as a configuration layer above the environment and
below every override of the run (`--set`, writing flags, research flags, and
request fields). Errors in its values SHALL name the preset file. So a preset wins over the defaults, the profile, the
environment, and the server's global settings, and loses to anything the
user sets for the run. An unknown depth name SHALL fail before any provider
is called, with an error that lists the known presets. The depth `custom`
SHALL apply no preset.

#### Scenario: Flag beats preset
- **WHEN** the user runs with depth `deep` and `--words 800`
- **THEN** the resolved `write.words` is 800 and `plan.max_sub_queries` is 6

#### Scenario: Preset beats environment
- **WHEN** `WOSARCHER_PLAN__MAX_SUB_QUERIES=4` is set and the run uses depth `quick`
- **THEN** the resolved `plan.max_sub_queries` is 3

#### Scenario: Unknown depth
- **WHEN** the user runs with depth `huge`
- **THEN** the command fails with an error listing `quick`, `standard`, `deep`, `exhaustive`

### Requirement: Depth commands
The CLI SHALL provide `wosarcher depth list` (one line per preset: the name
and its description) and `wosarcher depth show NAME` (the keys the preset
sets with their values, or "sets nothing; uses the defaults" for
`standard`). An unknown name SHALL fail with exit status 2 and the list of
known presets.

#### Scenario: List
- **WHEN** the user runs `wosarcher depth list`
- **THEN** four lines show `quick`, `standard`, `deep`, and `exhaustive` with their descriptions

#### Scenario: Show
- **WHEN** the user runs `wosarcher depth show quick`
- **THEN** the output lists `plan.max_sub_queries = 3` through `write.words = 600`

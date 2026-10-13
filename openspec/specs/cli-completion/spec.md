# cli-completion Specification

## Purpose

A zsh completion for the `wosarcher` client that completes its commands,
flags, and option values, including run IDs, profiles, and depth presets
asked from the daemon, and stays in step with the CLI.

## Requirements

### Requirement: Commands and flags
The completion SHALL offer, for `wosarcher`, every top-level command with
its one-line help as description (`run`, `fork`, `runs`, `logs`, `cancel`,
`export`, `doctor`, `profile`, `providers`, `depth`, `tokens`, `schema`),
the subcommands of `profile` (`list`, `show`), `providers` (`list`),
`depth` (`list`, `show`), and `tokens` (`new`, `list`, `revoke`), and for
each command exactly the flags that command accepts, each with a
description. A flag that takes no value SHALL be offered once; a
repeatable flag (`--attach`, `--set`, `--use`, `--allow-domain`,
`--block-domain`, `--block`) SHALL stay offered after use.

#### Scenario: Top-level commands
- **WHEN** the user types `wosarcher ` and presses Tab
- **THEN** the twelve commands are offered with descriptions

#### Scenario: Flags of one command
- **WHEN** the user types `wosarcher fork 20260101-000000-abcd --` and presses Tab
- **THEN** `--from`, `--use`, and `--json` are offered and `--attach` and `--depth` are not

#### Scenario: Repeatable flag
- **WHEN** the user types `wosarcher run q --use score=bm25 --u` and presses Tab
- **THEN** `--use` is offered again

### Requirement: Static option values
The completion SHALL complete these values without a connection: stage names
for `--until` and `--from`; `files`, `web`, `both` for `--sources`;
`report`, `answer` for `run` and `fork` `--format`; `pdf`, `docx` for
`export --format`; `numeric`, `superscript`, `author-year` for
`--citation-marker`; `APA`, `MLA`, `Chicago`, `IEEE` for
`--reference-style`; the built-in tone names for `--tone`; `none`, `low`,
`medium`, `high`, `default` for the `--*-thinking` flags; `all` and `auto`
for `--search-language`; `auto` for `--context-tokens` and
`--gap-context-tokens`; the block names for `doctor --block`,
`providers list --block`, and the part of `--use` before `=`; files and
directories for `--attach`; and files for `export --output`.

#### Scenario: Stage values
- **WHEN** the user types `wosarcher run q --until ` and presses Tab
- **THEN** `load`, `plan`, `search`, `fetch`, `chunk`, `prefilter`, `score`, `gap`, `select`, and `write` are offered

#### Scenario: Export formats
- **WHEN** the user types `wosarcher export 20260101-000000-abcd --format ` and presses Tab
- **THEN** `pdf` and `docx` are offered, and `report` is not

#### Scenario: Use blocks
- **WHEN** the user types `wosarcher run q --use ` and presses Tab
- **THEN** `search=`, `fetch=`, `prefilter=`, `score=`, and `llm=` are offered

### Requirement: Values from the daemon
The completion SHALL ask the daemon through the `wosarcher` command being
completed, never by reading a profile, an entry, a run directory, or a
secret: run IDs from `wosarcher runs --json`, described by their query,
for the run ID argument of `fork`, `logs`, `cancel`, and `export`; profile
names from `wosarcher profile list` for `--profile` and `profile show`;
entry names of the typed block from `wosarcher providers list --block
BLOCK --json` for the part of `--use` after `=`; and depth preset names
from `wosarcher depth list` for `--depth` and `depth show`. It SHALL use
the same connection environment as the command (`WOSARCHER_URL`,
`WOSARCHER_TOKEN`, `WOSARCHER_SOCKET`).

#### Scenario: Run IDs with queries
- **WHEN** the daemon has runs `20260101-000000-abcd` ("what is rrf") and `20260102-000000-ef01` and the user types `wosarcher logs ` and presses Tab
- **THEN** both IDs are offered, `20260101-000000-abcd` described by `what is rrf`

#### Scenario: Profiles
- **WHEN** the daemon has the profiles `lan` and `default` and the user types `wosarcher run q --profile ` and presses Tab
- **THEN** `lan` and `default` are offered

#### Scenario: Entry names
- **WHEN** the daemon has the score entries `bm25`, `jev-strict`, and `rerank` and the user types `wosarcher run q --use score=` and presses Tab
- **THEN** `score=bm25`, `score=jev-strict`, and `score=rerank` are offered

#### Scenario: Depth presets
- **WHEN** the daemon has the user preset `wide` and the user types `wosarcher depth show ` and presses Tab
- **THEN** `quick`, `standard`, `deep`, `exhaustive`, and `wide` are offered

### Requirement: Quiet failure
When the daemon cannot be reached, refuses the request, or does not answer
within 2 seconds, a dynamic completion SHALL offer no values, SHALL print
nothing on the terminal, and SHALL return the prompt to the user.

#### Scenario: No daemon
- **WHEN** nothing listens on the client's socket and the user types `wosarcher cancel ` and presses Tab
- **THEN** no candidates are offered, no error text appears, and the prompt is usable at once

### Requirement: Completion matches the CLI
`scripts/check` SHALL fail when the completion and the `wosarcher` Typer app
disagree: a command or subcommand the app defines that the completion lacks,
a flag a command accepts that the completion does not offer for that
command, a command or flag the completion offers that the app does not
define, or a static value list that differs from the values the package
defines (stages, sources, run and export formats, citation markers,
thinking levels, tones, doctor blocks). The failure SHALL name the command
and flag.

#### Scenario: New tone without completion
- **WHEN** a developer adds a tone `neutral` to the built-in tones without changing the completion and runs `scripts/check`
- **THEN** the check fails naming `--tone` and `neutral`

#### Scenario: New flag without completion
- **WHEN** a developer adds `--since` to `wosarcher runs` without changing the completion and runs `scripts/check`
- **THEN** the check fails naming `runs` and `--since`

#### Scenario: Removed flag left in completion
- **WHEN** the completion offers `--force` for `cancel`, which the app does not define, and the developer runs `scripts/check`
- **THEN** the check fails naming `cancel` and `--force`

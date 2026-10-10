# agent-skill Specification

## Purpose

Gives AI agents an accurate guide to using wosarcher through its CLI, and
keeps that guide consistent with the real commands, flags, and published
JSON Schema.

## Requirements

### Requirement: Skill file
The repository SHALL contain `skill/SKILL.md` with a frontmatter `name`
(`wosarcher`) and a `description` that says when an agent should use it
(researching a question on the web or in local files and getting cited
passages or a cited report).

#### Scenario: Frontmatter
- **WHEN** an agent loads `skill/SKILL.md`
- **THEN** its frontmatter has `name: wosarcher` and a non-empty `description`

### Requirement: Documented uses
The skill SHALL document, each with a command example:

- getting cited context with `wosarcher run "<query>" --until select --json`, as the recommended default for agents;
- getting a full report with `wosarcher run "<query>" --json`;
- getting a short cited answer with `wosarcher run "<query>" --format answer --json`;
- attaching files with `--attach` and choosing sources with `--sources files|web|both`;
- choosing a profile with `--profile`, listing profiles with `wosarcher profile list`, and overriding fields with `--set`;
- writing options `--tone`, `--tone-instructions`, `--words`, `--language`, `--citation-marker`, `--reference-style`, and `--format`;
- rewriting a finished run with `wosarcher fork <run_id> --from write`;
- listing runs with `wosarcher runs --json` and checking providers with `wosarcher doctor`.

#### Scenario: Cited context first
- **WHEN** an agent reads the skill
- **THEN** the first command example is `wosarcher run "<query>" --until select --json`

#### Scenario: Answer example
- **WHEN** an agent reads the skill
- **THEN** it finds `wosarcher run "<query>" --format answer --json` described as the way to get a short cited answer

### Requirement: Output description
The skill SHALL describe the JSON document printed by `--json` (run ID,
status, error, context passages with number, source, heading path, text,
and score, and the report), how to cite a passage by its number, the exit
codes (0, 1, 2, 69, 130), that the commands talk to a running `wosarcherd`
(over the local socket, or `WOSARCHER_URL` with `WOSARCHER_TOKEN`), and
SHALL point to `wosarcher schema` and its `RunOutput` definition for the
full schema. It SHALL include one example output document.

#### Scenario: Example matches the contract
- **WHEN** the example output in the skill is parsed as `RunOutput`
- **THEN** it validates without error

#### Scenario: Connection documented
- **WHEN** an agent reads the skill
- **THEN** it finds exit code 69 explained as "the daemon is not reachable" and the two environment variables for a remote daemon

### Requirement: Commands match the CLI
Every command line in the skill's code blocks that starts with `wosarcher`
SHALL name an existing command or subcommand, every option it uses SHALL
exist on that command, and the line SHALL parse as the CLI parses it: every
required argument and required option present and every typed option value
(such as `--words`) of the right type. Placeholders written in angle
brackets (`<query>`, `<run_id>`, `<profile>`) SHALL count as present
values. The values the skill gives SHALL be accepted by the rules the CLI
applies: `--sources` one of `both`, `web`, `files` (and `files` only with
`--attach`); `--until` and `--from` a stage name; `--tone` a known tone;
`--citation-marker` and `--reference-style` a known marker and style; and
each `--set` entry a valid configuration override. This SHALL be checked by
an automated test.

#### Scenario: Unknown flag
- **WHEN** the skill documents `wosarcher run "q" --format json`
- **THEN** the test fails naming `--format` and the `run` command

#### Scenario: Unknown command
- **WHEN** the skill documents `wosarcher replay <id>`
- **THEN** the test fails naming `replay`

#### Scenario: Missing required option
- **WHEN** the skill documents `wosarcher fork <run_id> --json`
- **THEN** the test fails naming the missing `--from` option

#### Scenario: Missing argument
- **WHEN** the skill documents `wosarcher run --json`
- **THEN** the test fails naming the missing `QUERY` argument

#### Scenario: Invalid value
- **WHEN** the skill documents `wosarcher run "q" --sources filez --until rank`
- **THEN** the test fails naming `--sources` with `filez` and `--until` with `rank`

#### Scenario: Invalid override
- **WHEN** the skill documents `wosarcher run "q" --set select.no_such_field=1`
- **THEN** the test fails naming `select.no_such_field`

### Requirement: Schema names match
Every schema type name the skill refers to in backticks followed by the
word "definition" or listed under its schema section SHALL exist in the
output of `wosarcher schema`. This SHALL be checked by an automated test.

#### Scenario: Renamed contract
- **WHEN** `RunOutput` is renamed in the code but not in the skill
- **THEN** the test fails naming `RunOutput`

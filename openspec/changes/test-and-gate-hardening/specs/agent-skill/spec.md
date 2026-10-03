# Spec Delta

## MODIFIED Requirements

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

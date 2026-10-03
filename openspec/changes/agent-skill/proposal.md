# Proposal

## Why

AI agents are one of the three ways wosarcher is used. They need a short,
accurate guide to the CLI: how to get cited context they can reason over,
how to get a full report, and how to read the JSON output. A guide that
drifts from the CLI is worse than none, so its commands must be checked
against the real command line on every test run.

## What Changes

- `skill/SKILL.md`: an agent skill (frontmatter `name`, `description`) that
  documents:
  - cited context: `wosarcher run "q" --until select --json`;
  - a full report: `wosarcher run "q" --json`;
  - attachments (`--attach`), sources (`--sources files|web|both`),
    profiles (`--profile`, `wosarcher profile list`), overrides (`--set`),
    writing options (`--tone`, `--words`, `--language`,
    `--citation-marker`, `--reference-style`, `--tone-instructions`);
  - rewriting a finished run with `wosarcher fork <id> --from write`;
  - listing runs (`wosarcher runs --json`) and checking providers
    (`wosarcher doctor`);
  - the output: the main fields of the `RunOutput` document, exit codes,
    and `wosarcher schema` as the full JSON Schema.
- `tests/test_skill.py`: parses every `wosarcher` command line in
  SKILL.md's code blocks and checks each subcommand and flag against the
  typer app; checks that every schema type name the skill mentions exists
  in `wosarcher schema`; validates the skill's example output against
  `RunOutput`.

## Non-goals

- No MCP server and no new CLI command; the skill uses the CLI as it is.
- No server or HTTP API usage in the skill (local CLI only, no auth).
- No installer; installing the skill is copying or linking `skill/` into an
  agent's skills directory, described in the skill's own header comment.
- No change to `wosarcher` behaviour.

## Capabilities

### New Capabilities

- `agent-skill`: the agent-facing guide to the CLI and the checks that keep
  it consistent with the CLI and the published schema.

### Modified Capabilities

None.

## Impact

- New files: `skill/SKILL.md`, `tests/test_skill.py`.
- Relies only on the CLI: run-orchestration (`run`, `fork`, `runs`,
  `--json`, `RunOutput`), core-contracts (`profile`, `schema`),
  provider-adapters (`doctor`). Does not use server-api, admin-auth, or the
  frontend changes.
- No new dependencies.
- docs/design.md sections implemented: Agent skill, Package layout
  (`skill/SKILL.md`). The Agent skill section gains a sentence on the
  consistency test.

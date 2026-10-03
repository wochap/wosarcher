# Design

## Context

By this change the CLI has `run`, `fork`, `runs` (run-orchestration),
`profile list|show|use` and `schema` (core-contracts), and `doctor`
(provider-adapters). `wosarcher run --json` prints a `RunOutput` document,
and `wosarcher schema` prints one JSON Schema document whose `$defs`
include `RunOutput`, `Context`, and `Report`. The typer app lives in
`wosarcher.cli` (`cli/__init__.py`). See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**

- A skill an agent can read in one pass (under 150 lines) and act on.
- Drift between the skill and the CLI fails the test suite.

**Non-Goals:**

- Documenting every flag; the skill names the useful ones and points to
  `wosarcher <command> --help`.
- The HTTP API (routes under `/api`); agents on the same machine use the
  CLI and need no authentication.

## Decisions

### Skill structure

```
---
name: wosarcher
description: Research a question on the web and/or in local Markdown files and get cited passages or a cited report, using the local `wosarcher` CLI. Use when ...
---
# wosarcher
1. Cited context (default)       wosarcher run "<query>" --until select --json
2. Full report                   wosarcher run "<query>" --json
3. Local files                   --attach, --sources files|web|both
4. Profiles and overrides        --profile, wosarcher profile list, --set
5. Writing options               --tone ... --reference-style
6. Rewrite a finished run        wosarcher fork <run_id> --from write --tone critical --json
7. Runs and providers            wosarcher runs --json, wosarcher doctor
8. Output                        RunOutput fields, citing [n], exit codes, example
9. Schema                        wosarcher schema; definitions RunOutput, Context, Report
```

Guidance for agents, stated in the skill: prefer `--until select` (cheaper,
faster, and the agent writes its own answer citing passage numbers);
progress goes to stderr, so read only stdout; a long run can be followed in
`<run_dir>/events.jsonl`; exit 2 means fix the arguments, 1 means read
`error`.

How to install is one comment line under the frontmatter: copy or symlink
`skill/` to the agent's skills directory as `wosarcher/`.

### Consistency test reads the click command tree

`tests/test_skill.py`:

1. Extract command lines: inside fenced code blocks, every line whose first
   token is `wosarcher` (continuation lines ending in `\` joined).
2. Tokenise with `shlex.split`. Placeholders such as `<query>` and
   `<run_id>` are positional values and need no check.
3. Get the click command with `typer.main.get_command(app)`. Walk tokens:
   while the current command is a `click.Group` and the next token is not
   an option, descend into `group.commands[token]` (missing → fail naming
   the token). Then every token starting with `--` must be in the union of
   `param.opts` of the final command (the part before `=` for
   `--opt=value`).
4. Schema names: collect names in the skill's "Schema" section written as
   `` `Name` definition`` or listed there in backticks; each must be a key
   in `json.loads(schema output)["$defs"]` (the schema command output is
   captured with `CliRunner`).
5. Example output: the first ```` ```json ```` block after the "Output"
   heading is parsed with `RunOutput.model_validate_json`.

Alternative: run `wosarcher <cmd> --help` and grep the text. Rejected: help
text formatting changes with rich and terminal width; the click tree is the
same data without parsing prose.

The test also checks the inverse for one case: the skill must contain the
exact string `wosarcher run "<query>" --until select --json` as its first
command line (spec: Cited context first).

## Risks / Trade-offs

- [The schema output's top-level key is not `$defs`] → core-contracts uses
  `models_json_schema`, which produces `$defs`; the test reads it from one
  helper so a change is a one-line fix.
- [Skill wording drifts while flags stay valid] → Out of scope for an
  automatic check; behaviour-level drift is caught by the example output
  validation and by review.

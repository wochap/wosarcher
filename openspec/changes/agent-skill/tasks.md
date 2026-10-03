# Tasks

## 1. Consistency test helpers

- [ ] 1.1 In `tests/test_skill.py`, implement `command_lines(markdown: str) -> list[list[str]]` (fenced blocks, lines starting with `wosarcher`, `\` continuations joined, `shlex.split`); verify a unit test on an inline Markdown sample with a continuation line and a non-wosarcher line
- [ ] 1.2 Implement `check_command(tokens) -> list[str]` walking `typer.main.get_command(wosarcher.cli.app)` as in design.md; verify unit tests that `wosarcher run "q" --format json` returns an error naming `--format` and `run`, that `wosarcher replay x` returns an error naming `replay`, and that `wosarcher profile list` returns none (spec: Commands match the CLI)
- [ ] 1.3 Implement `schema_defs() -> set[str]` from `wosarcher schema` output via `CliRunner`, and `skill_schema_names(markdown) -> set[str]`; verify a unit test that a sample naming `` `NoSuchType` definition`` is reported (spec: Schema names match)

## 2. Skill

- [ ] 2.1 Write `skill/SKILL.md` with frontmatter `name: wosarcher` and a `description`, the install comment, and sections 1 to 9 from design.md; the first command line is `wosarcher run "<query>" --until select --json`; under 150 lines; verify by reading it against the agent-skill spec's Documented uses list (spec: Skill file, Documented uses)
- [ ] 2.2 Add the Output section: `RunOutput` fields, citing passages by number, exit codes 0, 1, 2, 130, and one `json` example produced by running `wosarcher run "q" --until select --json` against the recorded-run fixture (`tests/fixtures/profiles/e2e.toml` with the recorded responses) and trimming passage text; verify by step 3.3 (spec: Output description)

## 3. Tests over the real skill

- [ ] 3.1 `test_skill_frontmatter`: frontmatter has `name: wosarcher` and a non-empty `description`, and the first command line equals `wosarcher run "<query>" --until select --json` (spec: Skill file, Cited context first)
- [ ] 3.2 `test_skill_commands_exist`: every command line in `skill/SKILL.md` passes `check_command`; the failure message lists every bad command and flag (spec: Commands match the CLI)
- [ ] 3.3 `test_skill_example_output`: the Output section's `json` block validates with `RunOutput.model_validate_json` (spec: Output description)
- [ ] 3.4 `test_skill_schema_names`: every schema name in the skill is in `schema_defs()` (spec: Schema names match)

## 4. Documentation

- [ ] 4.1 Update the "Agent skill" section of docs/design.md: where the skill lives, how to install it (copy or link `skill/`), and that `tests/test_skill.py` checks its commands, flags, schema names, and example against the CLI; verify the section matches the files
- [ ] 4.2 Verify `scripts/check --full` passes and `openspec validate agent-skill --strict` passes

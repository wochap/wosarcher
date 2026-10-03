# Design: test-and-gate-hardening

## Context

See proposal.md for why. Current state that shapes the approach:

- `.gitignore` line `runs/` matches any directory named `runs`, so
  `tests/fixtures/runs/20260101-000000-fixture/` is untracked. Its
  `request.json` holds the generator's temporary `runs_dir` and
  `cache_dir` (`/tmp/tmp…/runs`).
- `tests/test_skill.py::check_command` walks the Typer command tree and
  compares option names only. The CLI validates `--sources`, `--until`,
  `--from` in the command body (`cli/run.py` `stage_option`,
  `get_args(Sources)`), tones in `stages/write.py` `tone_description`,
  styles in `stages/write.py` `style`, the marker through `WritingOptions`,
  and `--set` through `config.resolve`.
- `scripts/check_architecture.py` uses a module-level `ROOT`; its
  `imported_modules` records only the base module for level-0
  `from X import name`; `check_adapter_independence` returns early for
  `adapters/__init__.py` and for names with fewer than three parts;
  `IO_LIBRARIES` lists third-party libraries only. Today's tree has no
  violation of the stricter rules (checked: pure parts import
  `urllib.parse`, `hashlib`, `asyncio`, `PurePosixPath`, and, in
  `prompts`, `importlib.resources`).
- `stages/write.py` `mla`, `chicago`, `ieee` append `.` after
  `year(source)`, which is `n.d.` for undated sources.
- `evals/judge.py` `parse_answer` calls `json.loads` on the matched list;
  a `JSONDecodeError` propagates to `main`, which exits 2.

## Goals / Non-Goals

**Goals:** every test named in the tasks can fail for the bug it guards;
the gate catches the five probed misses; no new dependency.

**Non-Goals:** see proposal.md "Non-goals". The gate does not try to catch
dynamic tricks beyond `__import__` and `importlib` (for example `getattr`
on `builtins`); it guards against natural mistakes, not adversaries.

## Decisions

1. **Ignore rule.** Change `runs/` to `/runs/` (the default runs directory
   at the repository root is the only one meant to be ignored). Alternative
   `!tests/fixtures/runs/` keeps a broad rule plus an exception; anchoring
   is simpler and states the intent.

2. **No machine paths in the fixture.** `make_recorded_run.py` replaces the
   temporary root's path with the fixed string `/fixture` in every text file
   it copies. Alternative: redact `run.runs_dir`/`run.cache_dir` from
   `request.json` in the store; that changes runtime behavior for one test
   asset. Timestamps still change on regeneration; the fixture is
   regenerated only when contracts change, so diffs stay reviewable.

3. **Skill check parses like the CLI.** For each command line: walk to the
   command as today, then call click's `command.make_context(name, args)`
   inside `try/except click.UsageError` (Typer commands are click
   commands); this catches missing arguments and options, unknown options,
   and type errors with click's own message. Then validate values from the
   parsed `ctx.params` with the CLI's own rules: `STAGES` and
   `get_args(Sources)` from `wosarcher.models`, `--sources files` needs
   `attach`, `prompts.tones()` keys (case-insensitive), `stages.write.style`,
   `WritingOptions(citation_marker=…)`, and
   `config.resolve(None, set_entries + writing_overrides(...), env)` with
   `env` pointing `XDG_CONFIG_HOME` at a temporary directory (so the
   developer's profiles do not leak in). Each failure becomes one error
   string naming the line, option, and value. Alternative: invoke the CLI
   with `CliRunner` and a fake build; heavier, and a successful invocation
   would start a run.

4. **Architecture check takes a root.** Replace the module-level use of
   `ROOT` in `part_of`, `module_name`, `check_file` with a `root: Path`
   parameter and add `check_tree(root: Path) -> list[str]`; `main()` calls
   `check_tree(ROOT)`. The test imports the script with
   `importlib.util.spec_from_file_location` (scripts/ is not a package) and
   writes small packages under `tmp_path / "src" / "wosarcher"`. Keeps the
   script stdlib-only and runnable before `uv sync`.

5. **Import recording.** For every `ImportFrom`, record the base module and
   additionally `f"{base}.{alias.name}"` for each alias (not only for
   relative `from . import x`). For `from wosarcher.models import Chunk`
   that adds `wosarcher.models.Chunk`, which maps to the same part, so no
   false positive. `check_adapter_independence` uses the third name part
   when present and no longer exempts `adapters/__init__.py` (it is part
   "adapters" with own name `__init__`, so any other adapter name is a
   violation).

6. **I/O ban in pure parts.** One table `PURE_FORBIDDEN` of module
   prefixes: the existing third-party set plus `requests`, `aiohttp`, and
   the stdlib modules listed in the spec. A name matches when it equals a
   prefix or starts with `prefix + "."`, so `urllib.parse` and
   `http` (bare) are not caught but `urllib.request` and `http.client` are.
   `pathlib` is checked by imported name: `from pathlib import Path` (or
   `import pathlib`) fails; `PurePath`, `PurePosixPath`, `PureWindowsPath`
   pass. One exception table `PURE_EXCEPTIONS = {"prompts":
   {"importlib.resources"}}`. Calls are found by walking `ast.Call` nodes
   whose `func` is `ast.Name` with id `open` or `__import__`. `asyncio`
   stays allowed: stages use it for concurrency only, and its I/O entry
   points need sockets or processes the ban already covers in practice.

7. **Reference punctuation.** In `stages/write.py`, a helper
   `end(text) -> str` adds a period only when the text does not already end
   with one; `mla`, `chicago`, `ieee` use it where they currently append
   `.` after the year. The test expectations in `tests/stages/test_write.py`
   change from `n.d..` to `n.d.`.

8. **Judge parsing.** `parse_answer` catches `json.JSONDecodeError` (and a
   non-list or non-integer result) and returns `None`, which the caller
   already records as missing precision.

## Risks / Trade-offs

- [The stricter gate flags a legitimate future need, for example a stage
  that must read a file] → the rule in docs/development.md stands: move
  the I/O to the runner or an adapter; edit the tables only with a design
  reason.
- [Committed fixture drifts silently after a contract change] →
  `test_fixture_parses` fails on the committed copy and names the
  regenerate command; that is the intended signal.
- [Changes 1 and 2 change event or artifact shapes] → the fixture is
  regenerated in this change's first task group, after those changes are
  applied.
- [Skill check uses `config.resolve`, which reads built-in profiles] →
  isolated with a temporary `XDG_CONFIG_HOME`; built-in profiles are
  package data and stable.

## Migration Plan

None at runtime. Contributors with an existing local fixture copy see it
become tracked; `git status` shows it once as new files.

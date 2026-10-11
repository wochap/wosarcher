"""Check that completions/_wosarcher matches the `wosarcher` Typer app.

Compares, both ways, the commands and each command's flags (`--help` is
allowed everywhere), and each `# values: <name>` list with the package
constant it mirrors. Prints one line per mismatch and exits 1 on any.
The file's shape is described in its header comment.
"""

import re
import sys
from pathlib import Path
from typing import Any, get_args

import typer

from wosarcher import doctor, prompts
from wosarcher.cli import app
from wosarcher.cli.options import FORMATS
from wosarcher.models import STAGES, Effort, ExportFormat, Sources, WritingOptions

COMPLETION = Path(__file__).resolve().parent.parent / "completions" / "_wosarcher"
FUNCTION = re.compile(r"^(_wosarcher(?:_[a-z_]+)?)\(\) \{$", re.MULTILINE)
FLAG = re.compile(r"""^\s*["'](?:\*|\([^)]*\))?(--[a-z-]+)\[""")
BRACE = re.compile(r"""^\s*["']\([^)]*\)["']\{([^}]*)\}""")
MARKER = re.compile(r"^\s*# (values|commands): (\S+)$")

VALUES: dict[str, tuple[str, ...]] = {
    "stages": STAGES,
    "sources": get_args(Sources),
    "formats": FORMATS,
    "export-formats": get_args(ExportFormat),
    "citation-markers": get_args(WritingOptions.model_fields["citation_marker"].annotation),
    "efforts": get_args(Effort),
    "tones": tuple(prompts.tones()),
    "blocks": doctor.BLOCKS,
}
"""Each `# values:` list and the package values it must hold; the flags show which option uses it."""
VALUE_FLAGS = {
    "stages": "--until/--from",
    "sources": "--sources",
    "formats": "--format",
    "export-formats": "export --format",
    "citation-markers": "--citation-marker",
    "efforts": "--*-thinking",
    "tones": "--tone",
    "blocks": "doctor --block",
}


def app_commands() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Flags per command path (`run`, `profile show`) and subcommands per group (`wosarcher`, `profile`)."""
    flags: dict[str, set[str]] = {}
    groups: dict[str, set[str]] = {}

    def walk(command: Any, path: list[str]) -> None:
        children = getattr(command, "commands", None)
        if children is not None:
            groups[" ".join(path) or "wosarcher"] = set(children)
            for name, child in children.items():
                walk(child, [*path, name])
            return
        flags[" ".join(path)] = {
            opt for param in command.params if param.param_type_name == "option" for opt in param.opts
        }

    walk(typer.main.get_command(app), [])
    return flags, groups


def list_entries(lines: list[str], start: int) -> list[str]:
    """The entry names of the array opened on the line after `start`, up to a line holding only `)`."""
    entries: list[str] = []
    for line in lines[start + 2 :]:
        text = line.strip()
        if text == ")":
            break
        entries.append(re.sub(r"(?<!\\):.*", "", text.strip("'\"")))
    return entries


def read_completion(text: str) -> tuple[dict[str, set[str]], dict[str, list[str]], dict[str, list[str]]]:
    """Flags per function's command path, entries per `# commands:` group, entries per `# values:` list."""
    flags: dict[str, set[str]] = {}
    commands: dict[str, list[str]] = {}
    values: dict[str, list[str]] = {}
    headers = list(FUNCTION.finditer(text))
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        lines = text[header.end() : end].splitlines()
        path = header.group(1).removeprefix("_wosarcher").removeprefix("_").replace("_", " ")
        found: set[str] = set()
        for number, line in enumerate(lines):
            if match := FLAG.match(line):
                found.add(match.group(1))
            elif match := BRACE.match(line):
                found.update(name for name in match.group(1).split(",") if name.startswith("--"))
            elif match := MARKER.match(line):
                kind, name = match.groups()
                (values if kind == "values" else commands)[name] = list_entries(lines, number)
        found.discard("--help")
        if found:
            flags[path] = found
    return flags, commands, values


def mismatches(text: str) -> list[str]:
    app_flags, app_groups = app_commands()
    flags, commands, values = read_completion(text)
    errors: list[str] = []
    for group in sorted(app_groups.keys() | commands.keys()):
        prefix = "" if group == "wosarcher" else f"{group} "
        want, have = app_groups.get(group, set()), set(commands.get(group, []))
        errors += [f"{prefix}{name}: command missing from completion" for name in sorted(want - have)]
        errors += [f"{prefix}{name}: command not in the CLI" for name in sorted(have - want)]
    for path in sorted(app_flags.keys() | flags.keys()):
        if path not in app_flags:
            errors.append(f"{path}: completion offers {', '.join(sorted(flags[path]))} for an unknown command")
            continue
        want, have = app_flags[path] - {"--help"}, flags.get(path, set())
        errors += [f"{path}: {flag} missing from completion" for flag in sorted(want - have)]
        errors += [f"{path}: {flag} not in the CLI" for flag in sorted(have - want)]
    for name in sorted(VALUES.keys() | values.keys()):
        if name not in VALUES:
            errors.append(f"# values: {name}: no package constant to compare with")
            continue
        flag, want, have = VALUE_FLAGS[name], VALUES[name], values.get(name)
        if have is None:
            errors.append(f"{flag}: no '# values: {name}' list in the completion")
            continue
        errors += [f"{flag}: {value} missing from completion" for value in want if value not in have]
        errors += [f"{flag}: {value} not in the package" for value in have if value not in want]
    return errors


def main() -> int:
    errors = mismatches(COMPLETION.read_text(encoding="utf-8"))
    for error in errors:
        print(f"{COMPLETION.name}: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

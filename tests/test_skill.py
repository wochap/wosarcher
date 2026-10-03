"""`skill/SKILL.md` stays consistent with the CLI, the published schema, and `RunOutput`."""

import json
import re
import shlex
from pathlib import Path

import typer
from typer.core import TyperGroup
from typer.testing import CliRunner

from wosarcher.cli import app
from wosarcher.models import RunOutput

SKILL = Path(__file__).parents[1] / "skill" / "SKILL.md"
FIRST_COMMAND = 'wosarcher run "<query>" --until select --json'
FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL)


def command_lines(markdown: str) -> list[list[str]]:
    """Tokens of every `wosarcher` line inside fenced blocks, `\\` continuations joined."""
    commands: list[list[str]] = []
    for _, block in FENCE.findall(markdown):
        for line in block.replace("\\\n", " ").splitlines():
            tokens = shlex.split(line)
            if tokens and tokens[0] == "wosarcher":
                commands.append(tokens)
    return commands


def check_command(tokens: list[str]) -> list[str]:
    """Errors for an unknown subcommand or an option the final command does not take."""
    command = typer.main.get_command(app)
    path = ["wosarcher"]
    rest = tokens[1:]
    while isinstance(command, TyperGroup) and rest and not rest[0].startswith("-"):
        name = rest.pop(0)
        found = command.commands.get(name)
        if found is None:
            return [f"{' '.join(path)}: unknown command {name!r}"]
        command, path = found, [*path, name]
    opts = {opt for param in command.params for opt in param.opts}
    return [
        f"{' '.join(path)}: unknown option {token.split('=')[0]!r} on {path[-1]!r}"
        for token in rest
        if token.startswith("--") and token.split("=")[0] not in opts
    ]


def schema_defs() -> set[str]:
    result = CliRunner().invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    return set(json.loads(result.stdout)["$defs"])


def section(markdown: str, title: str) -> str:
    match = re.search(rf"^## (?:\d+\. )?{title}\n(.*?)(?=^## |\Z)", markdown, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def skill_schema_names(markdown: str) -> set[str]:
    """Names written as `Name` definition(s) anywhere, plus capitalised backticked names in the Schema section."""
    names = set(re.findall(r"`([A-Za-z_]\w*)` definitions?", markdown))
    names |= set(re.findall(r"`([A-Z]\w*)`", section(markdown, "Schema")))
    return names


def test_command_lines_sample() -> None:
    sample = 'text\n```sh\nwosarcher run "a b" \\\n  --json\nls -la\n```\n'
    assert command_lines(sample) == [["wosarcher", "run", "a b", "--json"]]


def test_check_command_sample() -> None:
    [flag] = check_command(["wosarcher", "run", "q", "--format", "json"])
    assert "--format" in flag
    assert "'run'" in flag
    [command] = check_command(["wosarcher", "replay", "x"])
    assert "replay" in command
    assert check_command(["wosarcher", "profile", "list"]) == []


def test_skill_schema_names_sample() -> None:
    assert "NoSuchType" in skill_schema_names("See the `NoSuchType` definition.") - schema_defs()


def test_skill_frontmatter() -> None:
    text = SKILL.read_text()
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match
    fields = dict(line.split(": ", 1) for line in match.group(1).splitlines())
    assert fields["name"] == "wosarcher"
    assert fields["description"].strip()
    assert FIRST_COMMAND in text
    assert command_lines(text)[0] == shlex.split(FIRST_COMMAND)


def test_skill_commands_exist() -> None:
    errors = [error for tokens in command_lines(SKILL.read_text()) for error in check_command(tokens)]
    assert not errors, "\n".join(errors)


def test_skill_example_output() -> None:
    blocks = [body for lang, body in FENCE.findall(section(SKILL.read_text(), "Output")) if lang == "json"]
    assert blocks
    RunOutput.model_validate_json(blocks[0])


def test_skill_schema_names() -> None:
    names = skill_schema_names(SKILL.read_text())
    assert names
    assert not names - schema_defs(), sorted(names - schema_defs())

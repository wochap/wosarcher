"""`skill/SKILL.md` stays consistent with the CLI, the published schema, and `RunOutput`."""

import json
import re
import shlex
import tempfile
from pathlib import Path
from typing import Any, get_args

import typer
from typer._click.exceptions import MissingParameter, UsageError
from typer.core import TyperGroup
from typer.testing import CliRunner

from wosarcher.cli import app
from wosarcher.config import ConfigError, resolve
from wosarcher.daemon.run import writing_overrides
from wosarcher.models import STAGES, RunOutput, Sources, WritingOptions
from wosarcher.prompts import tones
from wosarcher.stages.write import style

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
    """Errors for an unknown subcommand or option, a line the CLI would not parse, or a value it would reject."""
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
    unknown = [
        f"{' '.join(path)}: unknown option {token.split('=')[0]!r} on {path[-1]!r}"
        for token in rest
        if token.startswith("--") and token.split("=")[0] not in opts
    ]
    if unknown:
        return unknown
    line = " ".join(tokens)
    try:
        ctx = command.make_context(path[-1], list(rest))
    except MissingParameter as error:
        param = error.param
        if param is None:
            return [f"{line}: {error.format_message()}"]
        kind = param.param_type_name
        name = (param.name or "").upper() if kind == "argument" else "/".join(param.opts)
        return [f"{line}: missing {kind} {name}"]
    except UsageError as error:
        return [f"{line}: {error.format_message()}"]
    if path[-1] in ("run", "fork"):
        return [f"{line}: {error}" for error in check_values(ctx.params)]
    return []


def check_values(params: dict[str, Any]) -> list[str]:
    """The value checks `wosarcher run` and `fork` apply before a run starts."""
    errors: list[str] = []
    sources = params.get("sources")
    if sources is not None and sources not in get_args(Sources):
        errors.append(f"--sources {sources!r} is not one of {', '.join(get_args(Sources))}")
    if sources == "files" and not params.get("attach"):
        errors.append("--sources files needs --attach")
    for option, key in (("--until", "until"), ("--from", "from_")):
        value = params.get(key)
        if value is not None and value not in STAGES:
            errors.append(f"{option} {value!r} is not a stage")
    tone = params.get("tone")
    if tone is not None and tone.lower() not in tones():
        errors.append(f"--tone {tone!r} is not a known tone")
    reference_style = params.get("reference_style")
    if reference_style is not None:
        try:
            style(reference_style)
        except ValueError as error:
            errors.append(f"--reference-style: {error}")
    marker = params.get("citation_marker")
    if marker is not None:
        try:
            WritingOptions(citation_marker=marker)
        except ValueError:
            errors.append(f"--citation-marker {marker!r} is not a known marker")
    flags = writing_overrides(
        **{
            key: params.get(key)
            for key in ("tone", "tone_instructions", "words", "language", "citation_marker", "reference_style")
        }
    )
    with tempfile.TemporaryDirectory() as config_home:
        try:
            resolve(None, [*(params.get("set_") or []), *flags], {"XDG_CONFIG_HOME": config_home})
        except (ConfigError, ValueError) as error:
            errors.append(f"--set: {error}")
    return errors


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
    [flag] = check_command(["wosarcher", "run", "q", "--style", "json"])
    assert "--style" in flag
    assert "'run'" in flag
    [command] = check_command(["wosarcher", "replay", "x"])
    assert "replay" in command
    assert check_command(["wosarcher", "profile", "list"]) == []


def test_check_command_missing_option() -> None:
    [error] = check_command(["wosarcher", "fork", "<run_id>", "--json"])
    assert "--from" in error


def test_check_command_missing_argument() -> None:
    [error] = check_command(["wosarcher", "run", "--json"])
    assert "QUERY" in error


def test_check_command_bad_values() -> None:
    errors = check_command(["wosarcher", "run", "q", "--sources", "filez", "--until", "rank"])
    assert len(errors) == 2
    assert "--sources" in errors[0]
    assert "filez" in errors[0]
    assert "--until" in errors[1]
    assert "rank" in errors[1]


def test_check_command_bad_override() -> None:
    [error] = check_command(["wosarcher", "run", "q", "--set", "select.no_such_field=1"])
    assert "select.no_such_field" in error


def test_check_command_bad_tone() -> None:
    errors = check_command(["wosarcher", "run", "q", "--tone", "sarcastic"])
    assert any("sarcastic" in error for error in errors)


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


def test_skill_connection() -> None:
    text = SKILL.read_text()
    assert "`69` the daemon is not reachable" in text
    assert "`WOSARCHER_URL`" in text
    assert "`WOSARCHER_TOKEN`" in text

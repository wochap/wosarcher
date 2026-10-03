"""Prompt files shipped as package data, loaded as `string.Template`.

Only trusted values (the query and options) are ever substituted; scraped
text is sent in separate data messages, never through a template.
"""

import tomllib
from importlib.resources import files
from string import Template
from typing import cast


def load(name: str) -> Template:
    """The template in `prompts/<name>.md`."""
    path = files(__name__).joinpath(f"{name}.md")
    if not path.is_file():
        raise FileNotFoundError(f"no prompt named '{name}' (looked for prompts/{name}.md)")
    return Template(path.read_text(encoding="utf-8"))


def tones() -> dict[str, str]:
    """The writing tones in `prompts/tones.toml`, keyed by lowercase name."""
    data = tomllib.loads(files(__name__).joinpath("tones.toml").read_text(encoding="utf-8"))
    entries = cast(dict[str, str], data["tones"])
    return {name.lower(): description for name, description in entries.items()}

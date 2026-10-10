"""Global defaults shared by the server and the CLI, stored as `<config_dir>/server-settings.json`."""

import logging
from pathlib import Path

from pydantic import ValidationError

from wosarcher.models import ServerSettings

FILE_NAME = "server-settings.json"

log = logging.getLogger(__name__)


def load(config_dir: Path) -> ServerSettings:
    """The stored settings; the built-in defaults when the file does not exist, or with a warning when it is invalid."""
    path = config_dir / FILE_NAME
    if not path.is_file():
        return ServerSettings()
    try:
        return ServerSettings.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        log.warning("%s is not valid, using the defaults: %s", path, error)
        return ServerSettings()


def save(config_dir: Path, settings: ServerSettings) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / FILE_NAME
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)

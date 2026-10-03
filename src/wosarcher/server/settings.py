"""Global defaults for runs started by the server, stored as `<config_dir>/server-settings.json`."""

from pathlib import Path

from wosarcher.models import ServerSettings

FILE_NAME = "server-settings.json"


def load(config_dir: Path) -> ServerSettings:
    """The stored settings, or the built-in defaults when the file does not exist."""
    path = config_dir / FILE_NAME
    if not path.is_file():
        return ServerSettings()
    return ServerSettings.model_validate_json(path.read_text(encoding="utf-8"))


def save(config_dir: Path, settings: ServerSettings) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / FILE_NAME
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)

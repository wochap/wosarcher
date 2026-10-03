from pathlib import Path

from wosarcher.models import ServerSettings, WritingOptions
from wosarcher.server import settings


def test_defaults_without_file(tmp_path: Path) -> None:
    assert settings.load(tmp_path / "missing") == ServerSettings()


def test_round_trip(tmp_path: Path) -> None:
    saved = ServerSettings(writing=WritingOptions(words=800, tone="formal"), sources="web")
    settings.save(tmp_path / "config", saved)
    assert settings.load(tmp_path / "config") == saved
    assert not list((tmp_path / "config").glob("*.tmp"))

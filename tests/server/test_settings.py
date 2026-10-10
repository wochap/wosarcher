from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wosarcher.models import ServerSettings, WritingOptions
from wosarcher.store import settings


def test_defaults_without_file(tmp_path: Path) -> None:
    assert settings.load(tmp_path / "missing") == ServerSettings()


def test_round_trip(tmp_path: Path) -> None:
    saved = ServerSettings(writing=WritingOptions(words=800, tone="formal"), sources="web")
    settings.save(tmp_path / "config", saved)
    assert settings.load(tmp_path / "config") == saved
    assert not list((tmp_path / "config").glob("*.tmp"))


def test_invalid_file_gives_defaults(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "server-settings.json").write_text('{"max_concurrent_runs": 0}')
    assert settings.load(tmp_path) == ServerSettings()
    assert "server-settings.json" in caplog.text


def test_limit_out_of_range(client: TestClient, config_dir: Path) -> None:
    response = client.put("/api/settings", json={"max_concurrent_runs": 9})
    assert response.status_code == 422
    assert "max_concurrent_runs" in response.json()["detail"]
    assert not (config_dir / "server-settings.json").exists()

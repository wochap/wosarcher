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


def test_questions_default(client: TestClient) -> None:
    found = client.get("/api/settings").json()["questions"]
    assert found == {"clarify": True, "rounds": True, "timeout": 60, "max_wait": 1800}


def test_questions_saved(client: TestClient, config_dir: Path) -> None:
    body = client.get("/api/settings").json()
    body["questions"]["timeout"] = 120
    assert client.put("/api/settings", json=body).status_code == 200
    assert client.get("/api/settings").json()["questions"]["timeout"] == 120
    assert settings.load(config_dir).questions.timeout == 120


def test_questions_out_of_range(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    body["questions"]["max_wait"] = 10
    response = client.put("/api/settings", json=body)
    assert response.status_code == 422
    assert "questions.max_wait" in response.json()["detail"]

import sys
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from typer.testing import CliRunner

from wosarcher.cli import app


@pytest.fixture
def calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)
    found: list[dict[str, Any]] = []

    def fake_run(application: Any, **options: Any) -> None:
        found.append({"app": application, **options})

    monkeypatch.setattr(uvicorn, "run", fake_run)
    return found


def test_defaults(calls: list[dict[str, Any]], tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 0, result.output
    [call] = calls
    assert (call["host"], call["port"], call["proxy_headers"]) == ("127.0.0.1", 8765, True)
    state = call["app"].state.server
    assert state.command == [sys.executable, "-m", "wosarcher"]
    assert state.runs_dir == tmp_path / "data" / "wosarcher" / "runs"
    assert state.config_dir == tmp_path / "config" / "wosarcher"


def test_port_option(calls: list[dict[str, Any]]) -> None:
    assert CliRunner().invoke(app, ["serve", "--port", "9000"]).exit_code == 0
    assert (calls[0]["host"], calls[0]["port"]) == ("127.0.0.1", 9000)

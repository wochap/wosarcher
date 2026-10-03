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
    assert (call["log_level"], call["forwarded_allow_ips"]) == ("info", "127.0.0.1")
    state = call["app"].state.server
    assert state.command == [sys.executable, "-m", "wosarcher"]
    assert state.runs_dir == tmp_path / "data" / "wosarcher" / "runs"
    assert state.config_dir == tmp_path / "config" / "wosarcher"


def test_port_option(calls: list[dict[str, Any]]) -> None:
    assert CliRunner().invoke(app, ["serve", "--port", "9000"]).exit_code == 0
    assert (calls[0]["host"], calls[0]["port"]) == ("127.0.0.1", 9000)


def test_lan_without_password_refused(calls: list[dict[str, Any]]) -> None:
    result = CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 2
    assert "wosarcher auth set-password" in result.output
    assert calls == []


def test_lan_with_password_starts(calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_AUTH__PASSWORD_HASH", "scrypt$15$8$1$salt$key")
    assert CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"]).exit_code == 0
    assert calls[0]["host"] == "0.0.0.0"


def test_localhost_name_allowed(calls: list[dict[str, Any]]) -> None:
    assert CliRunner().invoke(app, ["serve", "--host", "localhost"]).exit_code == 0
    assert CliRunner().invoke(app, ["serve", "--host", "127.0.0.2"]).exit_code == 0
    assert CliRunner().invoke(app, ["serve", "--host", "::1"]).exit_code == 0
    assert len(calls) == 3


def test_forwarded_allow_ips_setting(calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_SERVER__FORWARDED_ALLOW_IPS", '["172.17.0.1", "10.0.0.0/8"]')
    assert CliRunner().invoke(app, ["serve"]).exit_code == 0
    assert calls[0]["forwarded_allow_ips"] == "172.17.0.1,10.0.0.0/8"

"""The `wosarcher` client against a served daemon: connection, read-only commands, and `schema`."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import Daemon
from wosarcher.cli import app
from wosarcher.models import CONTRACTS

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("WOSARCHER_PROFILE", "WOSARCHER_LLM__API_KEY", "WOSARCHER_URL", "WOSARCHER_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def test_schema_offline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WOSARCHER_SOCKET", str(tmp_path / "nothing.sock"))
    first = runner.invoke(app, ["schema"])
    assert first.exit_code == 0
    assert first.output == runner.invoke(app, ["schema"]).output
    assert {model.__name__ for model in CONTRACTS} <= set(json.loads(first.output)["$defs"])


def test_daemon_not_running(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "nothing.sock"
    monkeypatch.setenv("WOSARCHER_SOCKET", str(path))
    result = runner.invoke(app, ["runs"])
    assert result.exit_code == 69
    assert str(path) in result.output
    assert "wosarcherd" in result.output


def test_socket_default(daemon: Daemon, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WOSARCHER_SOCKET")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(daemon.socket.parent))
    result = runner.invoke(app, ["runs"])
    assert result.exit_code == 0, result.output


def test_url_wins_over_socket(daemon: Daemon, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WOSARCHER_SOCKET", str(tmp_path / "nothing.sock"))
    monkeypatch.setenv("WOSARCHER_URL", daemon.url)
    assert runner.invoke(app, ["runs", "--json"]).output.strip() == "[]"


def test_unreachable_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_URL", "http://127.0.0.1:9")
    result = runner.invoke(app, ["runs"])
    assert result.exit_code == 69
    assert "http://127.0.0.1:9" in result.output


def test_depth_list(daemon: Daemon) -> None:
    result = runner.invoke(app, ["depth", "list"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert [line.split()[0] for line in lines] == ["quick", "standard", "deep", "exhaustive"]
    assert lines[0] == "quick  Fast overview: few searches, short report."


def test_depth_show(daemon: Daemon) -> None:
    lines = runner.invoke(app, ["depth", "show", "quick"]).output.splitlines()
    assert lines[0] == "sub_queries = 3"
    assert lines[-1] == "words = 600"


def test_depth_show_unknown(daemon: Daemon) -> None:
    result = runner.invoke(app, ["depth", "show", "huge"])
    assert result.exit_code == 2
    assert "quick, standard, deep, exhaustive" in result.output


def test_profile_list(daemon: Daemon, config_dir: Path) -> None:
    (config_dir / "profiles").mkdir(parents=True)
    (config_dir / "profiles" / "lan.toml").write_text('description = "LAN models"\n')
    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 0, result.output
    assert "  lan  (user)  LAN models" in result.output.splitlines()
    assert "* workstation  (builtin)" in result.output


def test_profile_show_redacts_key_file(daemon: Daemon, config_dir: Path, tmp_path: Path) -> None:
    secret = tmp_path / "llm-key"
    secret.write_text("sk-file-secret\n")
    (config_dir / "profiles").mkdir(parents=True)
    (config_dir / "profiles" / "lan.toml").write_text(f'[llm]\napi_key_file = "{secret}"\n')
    result = runner.invoke(app, ["profile", "show", "lan"])
    assert result.exit_code == 0, result.output
    assert 'api_key = "***"' in result.output
    assert "sk-file-secret" not in result.output


def test_profile_show_unknown(daemon: Daemon) -> None:
    result = runner.invoke(app, ["profile", "show", "nope"])
    assert result.exit_code == 2
    assert "workstation" in result.output

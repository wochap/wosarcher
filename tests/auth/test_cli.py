"""`wosarcherd auth set-password` and the client's `wosarcher tokens` commands."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import Daemon
from wosarcher.auth import AuthStore, verify_password
from wosarcher.cli import app as client
from wosarcher.daemon import app


@pytest.fixture
def auth_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)
    monkeypatch.delenv("WOSARCHER_AUTH__PASSWORD_HASH", raising=False)
    return tmp_path / "wosarcher" / "auth.json"


def invoke(*args: str, entered: str = "") -> tuple[int, str]:
    result = CliRunner().invoke(app, ["auth", *args], input=entered)
    return result.exit_code, result.output


def test_set_password_stores_hash(auth_file: Path) -> None:
    previous = os.umask(0o002)
    try:
        code, _ = invoke("set-password", entered="hunter22\nhunter22\n")
    finally:
        os.umask(previous)
    assert code == 0
    text = auth_file.read_text()
    assert "hunter22" not in text
    stored = json.loads(text)["password_hash"]
    assert stored.startswith("scrypt$")
    assert verify_password("hunter22", stored)
    assert auth_file.stat().st_mode & 0o777 == 0o600


def test_rewrite_keeps_mode(auth_file: Path) -> None:
    """The server rewriting `auth.json` (here: recording a token) leaves it 0600."""
    auth_file.parent.mkdir(parents=True)
    auth_file.write_text("{}")
    auth_file.chmod(0o664)
    AuthStore(auth_file).add_token("ci", datetime.now(UTC))
    assert auth_file.stat().st_mode & 0o777 == 0o600


def test_mismatch_stores_nothing(auth_file: Path) -> None:
    code, _ = invoke("set-password", entered="hunter22\nhunter23\n")
    assert code != 0
    assert not auth_file.exists()
    code, _ = invoke("set-password", entered="short\nshort\n")
    assert code != 0
    assert not auth_file.exists()


def test_print_does_not_store(auth_file: Path) -> None:
    code, output = invoke("set-password", "--print", entered="hunter22\nhunter22\n")
    assert code == 0
    assert verify_password("hunter22", output.strip().splitlines()[-1])
    assert not auth_file.exists()


def test_env_warning(auth_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_AUTH__PASSWORD_HASH", "scrypt$15$8$1$salt$key")
    code, output = invoke("set-password", entered="hunter22\nhunter22\n")
    assert code == 0
    assert "takes precedence" in output
    assert auth_file.exists()


def test_token_lifecycle_over_socket(daemon: Daemon, password_hash: str) -> None:
    store = AuthStore(daemon.config_dir / "auth.json")
    store.set_password(password_hash)
    runner = CliRunner()
    created = runner.invoke(client, ["tokens", "new", "laptop"])
    assert created.exit_code == 0, created.output
    token = next(line for line in created.output.splitlines() if line.startswith("wosarcher_"))
    listed = runner.invoke(client, ["tokens", "list"])
    assert "laptop" in listed.output
    assert token[-4:] in listed.output
    assert token not in listed.output
    [stored] = store.tokens()
    assert runner.invoke(client, ["tokens", "revoke", stored.id]).exit_code == 0
    assert store.tokens() == []
    assert runner.invoke(client, ["tokens", "revoke", stored.id]).exit_code == 2


def test_token_cannot_mint_tokens(daemon: Daemon, password_hash: str, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AuthStore(daemon.config_dir / "auth.json")
    store.set_password(password_hash)
    _, token = store.add_token("ci", datetime.now(UTC))
    monkeypatch.setenv("WOSARCHER_URL", daemon.url)
    monkeypatch.setenv("WOSARCHER_TOKEN", token)
    runner = CliRunner()
    assert runner.invoke(client, ["runs"]).exit_code == 0
    result = runner.invoke(client, ["tokens", "new", "x"])
    assert result.exit_code == 2
    assert "token routes need the socket or a browser session" in result.output


def test_revoked_token(daemon: Daemon, password_hash: str, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AuthStore(daemon.config_dir / "auth.json")
    store.set_password(password_hash)
    stored, token = store.add_token("ci", datetime.now(UTC))
    store.revoke(stored.id)
    monkeypatch.setenv("WOSARCHER_URL", daemon.url)
    monkeypatch.setenv("WOSARCHER_TOKEN", token)
    result = CliRunner().invoke(client, ["runs"])
    assert result.exit_code == 2
    assert "WOSARCHER_TOKEN" in result.output

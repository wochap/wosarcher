import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wosarcher.auth import verify_password
from wosarcher.cli import app


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
    code, _ = invoke("set-password", entered="hunter22\nhunter22\n")
    assert code == 0
    text = auth_file.read_text()
    assert "hunter22" not in text
    stored = json.loads(text)["password_hash"]
    assert stored.startswith("scrypt$")
    assert verify_password("hunter22", stored)
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


def test_token_lifecycle(auth_file: Path) -> None:
    code, output = invoke("new-token", "laptop")
    assert code == 0
    token = next(line for line in output.splitlines() if line.startswith("wosarcher_"))
    assert token not in auth_file.read_text()
    [stored] = json.loads(auth_file.read_text())["tokens"]
    code, listed = invoke("list-tokens")
    assert code == 0
    assert "laptop" in listed
    assert token[-4:] in listed
    assert token not in listed
    assert invoke("revoke-token", stored["id"])[0] == 0
    assert json.loads(auth_file.read_text())["tokens"] == []
    assert invoke("revoke-token", stored["id"])[0] != 0

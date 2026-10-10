from pathlib import Path

import pytest
from typer.testing import CliRunner

from wosarcher.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)


def test_profile_list_shows_descriptions() -> None:
    result = runner.invoke(app, ["profile", "list", "--profile", "cloud"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "  low-vram  (built-in)  Models take turns on one small GPU; slower, fits 8 GB." in lines
    assert "* cloud  (built-in)  Hosted APIs only; needs API keys." in lines


def test_profile_show_key_file(tmp_path: Path) -> None:
    secret = tmp_path / "llm-key"
    secret.write_text("sk-file-secret\n")
    profiles = tmp_path / "wosarcher" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "lan.toml").write_text(f'[llm]\napi_key_file = "{secret}"\n')
    result = runner.invoke(app, ["profile", "show", "lan"])
    assert result.exit_code == 0, result.output
    assert 'api_key = "***"' in result.output
    assert f'api_key_file = "{secret}"' in result.output
    assert "sk-file-secret" not in result.output

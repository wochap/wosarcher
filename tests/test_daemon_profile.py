"""`wosarcherd profile use`: the default profile in the daemon's config directory."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from wosarcher.config import resolve
from wosarcher.daemon import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)
    return tmp_path


def test_use_persists(config_home: Path) -> None:
    assert runner.invoke(app, ["profile", "use", "low-vram"]).exit_code == 0
    assert (config_home / "wosarcher" / "current").read_text().strip() == "low-vram"
    assert resolve(None, [], {"XDG_CONFIG_HOME": str(config_home)}).run.gpu_policy == "exclusive"


def test_use_unknown_profile_fails() -> None:
    result = runner.invoke(app, ["profile", "use", "nope"])
    assert result.exit_code == 2
    assert "unknown profile 'nope'" in result.output

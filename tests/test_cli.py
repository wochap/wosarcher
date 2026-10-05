import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wosarcher.cli import app
from wosarcher.models import CONTRACTS

runner = CliRunner()


@pytest.fixture(autouse=True)
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for name in ("WOSARCHER_PROFILE", "WOSARCHER_SCORE__API_KEY", "WOSARCHER_LLM__API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_list_marks_active_profile() -> None:
    assert runner.invoke(app, ["profile", "use", "cloud"]).exit_code == 0
    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 0
    assert "* cloud  (built-in)" in result.output
    assert "  low-vram  (built-in)" in result.output
    assert "  workstation  (built-in)" in result.output


def test_use_persists(config_home: Path) -> None:
    runner.invoke(app, ["profile", "use", "low-vram"])
    assert (config_home / "wosarcher" / "current").read_text().strip() == "low-vram"
    assert 'gpu_policy = "exclusive"' in runner.invoke(app, ["profile", "show"]).output


def test_use_unknown_profile_fails() -> None:
    result = runner.invoke(app, ["profile", "use", "nope"])
    assert result.exit_code == 1
    assert "unknown profile 'nope'" in result.output


def test_show_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_LLM__API_KEY", "sk-secret")
    result = runner.invoke(app, ["profile", "show", "cloud", "--set", "score.top_k=12"])
    assert result.exit_code == 0
    assert 'api_key = "***"' in result.output
    assert "top_k = 12" in result.output
    assert "sk-secret" not in result.output


def test_schema_is_stable_and_complete() -> None:
    first = runner.invoke(app, ["schema"]).output
    second = runner.invoke(app, ["schema"]).output
    assert first == second
    definitions = json.loads(first)["$defs"]
    assert {model.__name__ for model in CONTRACTS} <= set(definitions)


def test_depth_list() -> None:
    result = runner.invoke(app, ["depth", "list"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert [line.split()[0] for line in lines] == ["quick", "standard", "deep", "exhaustive"]
    assert lines[0] == "quick  Fast overview: few searches, short report."


def test_depth_show_quick() -> None:
    result = runner.invoke(app, ["depth", "show", "quick"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert lines[0] == "plan.max_sub_queries = 3"
    assert not any("max_context_tokens" in line for line in lines)
    assert lines[-1] == "write.words = 600"


def test_depth_show_standard() -> None:
    result = runner.invoke(app, ["depth", "show", "standard"])
    assert result.output == "sets nothing; uses the defaults\n"


def test_depth_show_unknown() -> None:
    result = runner.invoke(app, ["depth", "show", "huge"])
    assert result.exit_code == 2
    assert "quick, standard, deep, exhaustive" in result.output

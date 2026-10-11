"""The zsh completion in `completions/_wosarcher`, driven in a real zsh; skipped without zsh."""

import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from wosarcher.models import STAGES, RunSummary

pytestmark = pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not on PATH")

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "zsh"
COMMANDS = {"run", "fork", "runs", "logs", "cancel", "export", "doctor", "profile", "depth", "tokens", "schema"}
PROFILES = """\
* default  (builtin)  Local models
  lan  (user)  LAN server
"""
DEPTHS = """\
quick  A few sources
standard  The default
deep  More rounds
exhaustive  Everything
"""


@pytest.fixture
def stub(tmp_path: Path) -> Path:
    runs = [
        RunSummary(
            run_id="20260101-000000-abcd",
            query="what is rrf",
            status="done",
            created=datetime.now(UTC),
            profile="default",
        ),
        RunSummary(
            run_id="20260102-000000-ef01",
            query='a "quoted": query',
            status="done",
            created=datetime.now(UTC),
            profile="lan",
        ),
    ]
    (tmp_path / "runs.json").write_bytes(TypeAdapter(list[RunSummary]).dump_json(runs, indent=2))
    (tmp_path / "profiles.txt").write_text(PROFILES)
    (tmp_path / "depths.txt").write_text(DEPTHS)
    return tmp_path


def capture(line: str, stub_dir: Path, fail: bool = False) -> str:
    env = {**os.environ, "PATH": f"{FIXTURES}{os.pathsep}{os.environ['PATH']}", "WOSARCHER_STUB_DIR": str(stub_dir)}
    env.pop("WOSARCHER_STUB_FAIL", None)
    if fail:
        env["WOSARCHER_STUB_FAIL"] = "1"
    zsh = shutil.which("zsh") or "zsh"
    command = [zsh, "-f", str(FIXTURES / "capture.zsh"), str(ROOT / "completions"), line]
    return subprocess.run(command, env=env, capture_output=True, text=True, timeout=20, check=False).stdout


def complete(line: str, stub_dir: Path) -> dict[str, str]:
    """Candidates zsh offers for `line` and Tab, word -> description."""
    candidates: dict[str, str] = {}
    for entry in capture(line, stub_dir).splitlines():
        if not entry.startswith("! "):
            word, _, description = entry.partition(" -- ")
            candidates[word.strip()] = description.strip()
    return candidates


def test_top_level_commands(stub: Path) -> None:
    found = complete("wosarcher ", stub)
    assert set(found) == COMMANDS
    assert all(found[name] for name in COMMANDS)


def test_flags_of_one_command(stub: Path) -> None:
    found = complete("wosarcher fork 20260101-000000-abcd --", stub)
    assert {"--from", "--json"} <= set(found)
    assert "--attach" not in found
    assert "--depth" not in found


def test_repeatable_flag(stub: Path) -> None:
    assert "--set" in complete("wosarcher run q --set a=1 --s", stub)


def test_stage_values(stub: Path) -> None:
    assert set(complete("wosarcher run q --until ", stub)) == set(STAGES)


def test_export_formats(stub: Path) -> None:
    assert set(complete("wosarcher export 20260101-000000-abcd --format ", stub)) == {"pdf", "docx"}


def test_run_ids_with_queries(stub: Path) -> None:
    found = complete("wosarcher logs ", stub)
    assert set(found) == {"20260101-000000-abcd", "20260102-000000-ef01"}
    assert found["20260101-000000-abcd"] == "what is rrf"


def test_profiles(stub: Path) -> None:
    assert set(complete("wosarcher run q --profile ", stub)) == {"default", "lan"}


def test_depth_presets(stub: Path) -> None:
    assert set(complete("wosarcher depth show ", stub)) == {"quick", "standard", "deep", "exhaustive"}


def test_quiet_failure(stub: Path) -> None:
    started = time.monotonic()
    output = capture("wosarcher cancel ", stub, fail=True)
    assert time.monotonic() - started < 5
    assert output == ""

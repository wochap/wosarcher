"""The committed recorded run parses with the current contracts and forks without the network."""

import json
from pathlib import Path

import pytest
import respx
from pydantic import BaseModel
from typer.testing import CliRunner

from tests.fixtures.recorded import FIXTURE_RUN, RUNS, config_home, copy_fixture
from wosarcher.cli import app
from wosarcher.models import (
    Candidate,
    Chunk,
    Context,
    Hit,
    Page,
    Plan,
    Report,
    RunCosts,
    RunOutput,
    RunRecord,
    Score,
    parse_event,
)
from wosarcher.store import STAGE_ARTIFACTS

DOCUMENTS: dict[str, type[BaseModel]] = {
    "request.json": RunRecord,
    "plan.json": Plan,
    "context.json": Context,
    "report.json": Report,
    "costs.json": RunCosts,
}
LINES: dict[str, type[BaseModel]] = {
    "files.jsonl": Page,
    "initial.jsonl": Hit,
    "hits.jsonl": Hit,
    "pages.jsonl": Page,
    "chunks.jsonl": Chunk,
    "candidates.jsonl": Candidate,
    "scores.jsonl": Score,
}
REGENERATE = "rerun `uv run python -m tests.fixtures.make_recorded_run`"


def test_fixture_parses() -> None:
    run_dir = RUNS / FIXTURE_RUN
    expected = {name for names in STAGE_ARTIFACTS.values() for name in names}
    assert expected <= {*DOCUMENTS, *LINES, "report.md"}
    assert (run_dir / "report.md").is_file()
    for name, model in DOCUMENTS.items():
        try:
            model.model_validate_json((run_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            pytest.fail(f"{name} does not parse ({REGENERATE}): {error}")
    for name, model in LINES.items():
        try:
            for line in (run_dir / name).read_text(encoding="utf-8").splitlines():
                model.model_validate_json(line)
        except (OSError, ValueError) as error:
            pytest.fail(f"{name} does not parse ({REGENERATE}): {error}")
    for number, line in enumerate((run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines(), start=1):
        try:
            parse_event(line)
        except ValueError as error:
            pytest.fail(f"events.jsonl line {number} does not parse ({REGENERATE}): {error}")


def test_fixture_has_no_machine_paths() -> None:
    for path in (RUNS / FIXTURE_RUN).rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "/tmp/" not in text, path.name
            assert str(Path.home()) not in text, path.name


def test_fixture_forks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home(tmp_path / "config")))
    monkeypatch.setenv("WOSARCHER_RUN__RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("WOSARCHER_RUN__CACHE_DIR", str(tmp_path / "cache"))
    parent = copy_fixture(tmp_path / "runs")
    args = ["fork", parent, "--from", "score", "--set", "score.provider=bm25", "--until", "select", "--json"]
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert RunOutput.model_validate(json.loads(result.stdout)).status == "done"
    assert not router.calls

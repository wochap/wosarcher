"""`wosarcher export` against a daemon with the fake exporter."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import StartDaemon
from tests.fixtures.recorded import copy_fixture
from wosarcher.adapters.fakes import FakeExporter
from wosarcher.cli import app

runner = CliRunner()


@pytest.fixture
def run_id(runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    runs_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    return copy_fixture(runs_dir)


def test_export_to_default_path(run_id: str, tmp_path: Path, start_daemon: StartDaemon) -> None:
    exporter = FakeExporter()
    start_daemon(exporter=exporter)
    result = runner.invoke(app, ["export", run_id, "--format", "docx"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == f"{run_id}.docx"
    assert (tmp_path / f"{run_id}.docx").read_bytes() == b"PK-fake-docx"
    assert exporter.inputs[0][1] == "docx"


def test_existing_file(run_id: str, tmp_path: Path, start_daemon: StartDaemon) -> None:
    exporter = FakeExporter()
    start_daemon(exporter=exporter)
    (tmp_path / f"{run_id}.pdf").write_bytes(b"old")
    result = runner.invoke(app, ["export", run_id, "--format", "pdf"])
    assert result.exit_code == 2
    assert f"{run_id}.pdf" in result.output
    assert "--force" in result.output
    assert (tmp_path / f"{run_id}.pdf").read_bytes() == b"old"
    assert exporter.inputs == []
    forced = runner.invoke(app, ["export", run_id, "--format", "pdf", "--force", "--output", f"{run_id}.pdf"])
    assert forced.exit_code == 0
    assert (tmp_path / f"{run_id}.pdf").read_bytes() == b"%PDF-fake"


@pytest.mark.parametrize(
    ("args", "exporter", "code"),
    [
        (["--format", "pdf"], FakeExporter(missing={"pdf": ["typst"]}), 1),
        (["--format", "pdf"], FakeExporter(failure="typst: error"), 1),
        (["--format", "odt"], FakeExporter(), 2),
    ],
)
def test_exit_codes(run_id: str, start_daemon: StartDaemon, args: list[str], exporter: FakeExporter, code: int) -> None:
    start_daemon(exporter=exporter)
    result = runner.invoke(app, ["export", run_id, *args])
    assert result.exit_code == code
    if exporter.absent:
        assert "PDF export needs typst on the server" in result.output


def test_unknown_run_and_missing_report(run_id: str, runs_dir: Path, start_daemon: StartDaemon) -> None:
    start_daemon(exporter=FakeExporter())
    assert runner.invoke(app, ["export", "nope", "--format", "pdf"]).exit_code == 2
    (runs_dir / run_id / "report.json").unlink()
    assert runner.invoke(app, ["export", run_id, "--format", "pdf"]).exit_code == 2

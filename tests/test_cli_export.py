"""`wosarcher export` with the fake exporter."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.fixtures.recorded import copy_fixture
from wosarcher.adapters.fakes import FakeExporter
from wosarcher.cli import app
from wosarcher.cli import export as export_command

runner = CliRunner()


@pytest.fixture
def run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.delenv("WOSARCHER_PROFILE", raising=False)
    monkeypatch.setenv("WOSARCHER_RUN__RUNS_DIR", str(runs))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    return copy_fixture(runs)


def use(monkeypatch: pytest.MonkeyPatch, exporter: FakeExporter) -> FakeExporter:
    monkeypatch.setattr(export_command, "exporter", lambda: exporter)
    return exporter


def test_export_to_default_path(run_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = use(monkeypatch, FakeExporter())
    result = runner.invoke(app, ["export", run_id, "--format", "docx"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == f"{run_id}.docx"
    assert (tmp_path / f"{run_id}.docx").read_bytes() == b"PK-fake-docx"
    assert exporter.inputs[0][1] == "docx"


def test_existing_file(run_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = use(monkeypatch, FakeExporter())
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
def test_exit_codes(
    run_id: str, monkeypatch: pytest.MonkeyPatch, args: list[str], exporter: FakeExporter, code: int
) -> None:
    use(monkeypatch, exporter)
    assert runner.invoke(app, ["export", run_id, *args]).exit_code == code


def test_unknown_run_and_missing_report(run_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, FakeExporter())
    assert runner.invoke(app, ["export", "nope", "--format", "pdf"]).exit_code == 2
    (tmp_path / "runs" / run_id / "report.json").unlink()
    assert runner.invoke(app, ["export", run_id, "--format", "pdf"]).exit_code == 2

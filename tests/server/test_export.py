"""`GET /api/runs/{id}/export` with the fake exporter."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.recorded import copy_fixture
from tests.server.conftest import BASE_URL, MakeApp
from tests.server.test_runs import on_disk
from tests.stages.catalog_data import structure
from wosarcher.adapters.fakes import FakeExporter
from wosarcher.models import RunRequest


@pytest.fixture
def exporter() -> FakeExporter:
    return FakeExporter()


@pytest.fixture
def client(make_app: MakeApp, exporter: FakeExporter) -> Iterator[TestClient]:
    with TestClient(make_app(exporter=exporter), base_url=BASE_URL) as test_client:
        yield test_client


def test_download_pdf(client: TestClient, runs_dir: Path, exporter: FakeExporter) -> None:
    run_id = copy_fixture(runs_dir)
    response = client.get(f"/api/runs/{run_id}/export", params={"format": "pdf"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="{run_id}.pdf"'
    assert response.content == b"%PDF-fake"
    markdown, fmt = exporter.inputs[0]
    assert fmt == "pdf"
    assert markdown.startswith("# battery recycling\n\n2026-10-05 · 20260101-000000-fixture\n")
    assert "## References" in markdown


def test_context_run(client: TestClient, runs_dir: Path) -> None:
    run_id = copy_fixture(runs_dir)
    (runs_dir / run_id / "report.json").unlink()
    response = client.get(f"/api/runs/{run_id}/export", params={"format": "docx"})
    assert (response.status_code, response.json()["error"]) == (404, "report_not_found")


def test_unknown_run(client: TestClient, runs_dir: Path) -> None:
    response = client.get("/api/runs/nope/export", params={"format": "pdf"})
    assert (response.status_code, response.json()["error"]) == (404, "run_not_found")


def test_unknown_format(client: TestClient, runs_dir: Path) -> None:
    run_id = copy_fixture(runs_dir)
    for params in ({"format": "odt"}, {}):
        response = client.get(f"/api/runs/{run_id}/export", params=params)
        assert (response.status_code, response.json()["error"]) == (422, "invalid_format")
        assert "pdf" in response.json()["detail"]
        assert "docx" in response.json()["detail"]


def test_typst_missing(client: TestClient, runs_dir: Path, exporter: FakeExporter) -> None:
    exporter.absent["pdf"] = ["typst"]
    run_id = copy_fixture(runs_dir)
    response = client.get(f"/api/runs/{run_id}/export", params={"format": "pdf"})
    assert response.status_code == 503
    assert response.json() == {"error": "export_unavailable", "detail": "PDF export needs typst on the server"}
    assert client.get(f"/api/runs/{run_id}/export", params={"format": "docx"}).status_code == 200


def test_export_failed(client: TestClient, runs_dir: Path, exporter: FakeExporter) -> None:
    exporter.failure = "error: unknown table"
    run_id = copy_fixture(runs_dir)
    response = client.get(f"/api/runs/{run_id}/export", params={"format": "pdf"})
    assert response.status_code == 500
    assert response.json() == {"error": "export_failed", "detail": "error: unknown table"}


def test_catalog_report_export(client: TestClient, runs_dir: Path, exporter: FakeExporter) -> None:
    fixture = copy_fixture(runs_dir)
    on_disk(runs_dir, "c", ends=True, request=RunRequest(query="q", kind="catalog", structure=structure(output="both")))
    (runs_dir / "c" / "report.json").write_bytes((runs_dir / fixture / "report.json").read_bytes())
    response = client.get("/api/runs/c/export", params={"format": "pdf"})
    assert response.status_code == 200
    assert "## References" in exporter.inputs[0][0]


def test_table_catalog_has_no_report(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "c", ends=True, request=RunRequest(query="q", kind="catalog", structure=structure()))
    response = client.get("/api/runs/c/export", params={"format": "pdf"})
    assert (response.status_code, response.json()["error"]) == (404, "no_report")

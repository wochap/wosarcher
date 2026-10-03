from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.server.conftest import BASE_URL, MakeApp


@pytest.fixture
def build(tmp_path: Path) -> Path:
    path = tmp_path / "dist"
    (path / "assets").mkdir(parents=True)
    (path / "index.html").write_text("<html>app</html>")
    (path / "assets" / "app.js").write_text("console.log(1)")
    return path


def test_spa_fallback(make_app: MakeApp, build: Path) -> None:
    with TestClient(make_app(static_dir=build), base_url=BASE_URL) as client:
        assert client.get("/").text == "<html>app</html>"
        assert client.get("/assets/app.js").text == "console.log(1)"
        response = client.get("/runs/abc123")
        assert (response.status_code, response.text) == (200, "<html>app</html>")


def test_api_not_shadowed(make_app: MakeApp, build: Path) -> None:
    with TestClient(make_app(static_dir=build), base_url=BASE_URL) as client:
        assert client.get("/api/runs").json() == []
        response = client.get("/api/nothing")
        assert (response.status_code, response.json()["error"]) == (404, "not_found")


def test_no_build_404(client: TestClient) -> None:
    assert client.get("/").status_code == 404
    assert client.get("/api/runs").status_code == 200

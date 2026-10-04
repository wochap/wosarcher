import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.server.conftest import BASE_URL, MakeApp
from wosarcher.config import store_profile
from wosarcher.models import DoctorReport, ProviderHealth
from wosarcher.server.meta import health_report


def test_settings_persist_across_apps(make_app: MakeApp) -> None:
    with TestClient(make_app(), base_url=BASE_URL) as first:
        body = first.get("/api/settings").json()
        body["writing"]["words"] = 800
        assert first.put("/api/settings", json=body).status_code == 200
    with TestClient(make_app(), base_url=BASE_URL) as second:
        assert second.get("/api/settings").json()["writing"]["words"] == 800


def test_invalid_settings_unchanged(client: TestClient, config_dir: Path) -> None:
    body = client.get("/api/settings").json()
    body["writing"]["citation_marker"] = "footnote"
    response = client.put("/api/settings", json=body)
    assert response.status_code == 422
    assert "writing.citation_marker" in response.json()["detail"]
    assert not (config_dir / "server-settings.json").exists()
    assert client.get("/api/settings").json()["writing"]["citation_marker"] == "numeric"


def test_profiles_active_marked(client: TestClient, tmp_path: Path) -> None:
    store_profile("cloud", {"XDG_CONFIG_HOME": str(tmp_path / "config")})
    profiles = client.get("/api/profiles").json()
    assert {p["name"]: p["active"] for p in profiles}["cloud"] is True
    assert sum(p["active"] for p in profiles) == 1
    assert {p["source"] for p in profiles} == {"builtin"}


def test_health_mapping() -> None:
    rows = (
        ProviderHealth(block="score", provider="rerank", base_url="http://r", status="failed", error="refused"),
        ProviderHealth(block="prefilter", provider="bm25", status="built-in"),
        ProviderHealth(block="llm", provider="llm", base_url="http://l", status="ok", latency_ms=50, unload="no"),
        ProviderHealth(block="search", provider="searxng", base_url="http://s", status="ok", latency_ms=1840),
        ProviderHealth(block="fetch", provider="firecrawl", base_url="http://f", status="ok", latency_ms=120),
    )
    report = health_report("cloud", DoctorReport(providers=rows, warnings=("w",)))
    assert [(c.role, c.status) for c in report.checks] == [
        ("score", "down"),
        ("prefilter", "skipped"),
        ("llm", "degraded"),
        ("search", "degraded"),
        ("fetch", "ok"),
    ]
    assert report.checks[0].detail == "refused"
    assert report.checks[3].latency_ms == 1840
    assert report.checks[4].url == "http://f"
    assert (report.profile, report.warnings) == ("cloud", ["w"])


def test_ok_row_detail_is_note() -> None:
    row = ProviderHealth(block="score", provider="rerank", status="ok", note="probe score -3.25 (logit scale)")
    report = health_report("workstation", DoctorReport(providers=(row,)))
    assert (report.checks[0].status, report.checks[0].detail) == ("ok", "probe score -3.25 (logit scale)")


def test_health_profile_param(client: TestClient, runs_dir: Path) -> None:
    response = client.get("/api/providers/health", params={"profile": "cloud"})
    assert response.status_code == 200
    assert response.json()["profile"] == "cloud"
    assert json.loads((runs_dir / "doctor-argv.json").read_text()) == ["doctor", "--json", "--profile", "cloud"]


def test_health_failed_provider_still_200(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "failed")
    response = client.get("/api/providers/health")
    assert response.status_code == 200
    checks = {c["role"]: c for c in response.json()["checks"]}
    assert (checks["score"]["status"], checks["score"]["detail"]) == ("down", "refused")
    assert response.json()["profile"] == "workstation"


def test_health_failure_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "garbage")
    response = client.get("/api/providers/health")
    assert response.status_code == 502
    assert response.json()["error"] == "health_unavailable"


def test_profile_descriptions(client: TestClient, tmp_path: Path) -> None:
    profiles = tmp_path / "config" / "wosarcher" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "nixos.toml").write_text("[run]\n")
    described = {p["name"]: p["description"] for p in client.get("/api/profiles").json()}
    assert described["workstation"] == "One GPU fits all models; models stay loaded."
    assert described["nixos"] == ""


def test_health_release_and_policy() -> None:
    rows = (ProviderHealth(block="prefilter", provider="embeddings", status="ok", release="llama-swap"),)
    report = health_report("low-vram", DoctorReport(gpu_policy="exclusive", providers=rows))
    assert report.gpu_policy == "exclusive"
    assert report.checks[0].release == "llama-swap"

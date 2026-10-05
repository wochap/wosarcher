import json
from pathlib import Path
from typing import Any, Protocol

import pytest
from fastapi.testclient import TestClient

from tests.server.conftest import BASE_URL, MakeApp
from wosarcher.config import store_profile
from wosarcher.server import meta


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


def test_profile_descriptions(client: TestClient, tmp_path: Path) -> None:
    profiles = tmp_path / "config" / "wosarcher" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "nixos.toml").write_text("[run]\n")
    described = {p["name"]: p["description"] for p in client.get("/api/profiles").json()}
    assert described["workstation"] == "One GPU fits all models; models stay loaded."
    assert described["nixos"] == ""


class Answer(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


def checks(response: Answer) -> dict[str, dict[str, object]]:
    assert response.status_code == 200, response.text
    return {check["role"]: check for check in response.json()["checks"]}


def test_health_profile_param(client: TestClient, runs_dir: Path) -> None:
    response = client.get("/api/providers/health", params={"profile": "cloud"})
    assert response.status_code == 200
    assert response.json()["profile"] == "cloud"


def test_never_checked(client: TestClient, runs_dir: Path) -> None:
    by_role = checks(client.get("/api/providers/health"))
    assert not (runs_dir / "doctor-argv.json").exists()
    assert list(by_role) == ["search", "fetch", "prefilter", "score", "llm"]
    assert {(c["status"], c["checked_at"]) for c in by_role.values()} == {("unchecked", None)}


def test_builtin_skipped(client: TestClient) -> None:
    by_role = checks(client.get("/api/providers/health", params={"profile": "cloud"}))
    assert {role for role, c in by_role.items() if c["status"] == "skipped"} >= {"prefilter"}


def test_slow_provider(client: TestClient, runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "slow")
    checks(client.post("/api/providers/health/check"))
    (runs_dir / "doctor-argv.json").unlink()
    search = checks(client.get("/api/providers/health"))["search"]
    assert not (runs_dir / "doctor-argv.json").exists()
    assert (search["status"], search["latency_ms"]) == ("degraded", 1840)
    assert search["checked_at"] is not None


def test_failed_probe_in_check(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "failed")
    score = checks(client.post("/api/providers/health/check"))["score"]
    assert (score["status"], score["detail"]) == ("down", "refused")
    assert score["checked_at"] is not None
    stored = checks(client.get("/api/providers/health"))["score"]
    assert (stored["status"], stored["detail"]) == ("down", "refused")


def test_configuration_changed(client: TestClient, tmp_path: Path) -> None:
    checks(client.post("/api/providers/health/check"))
    profiles = tmp_path / "config" / "wosarcher" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "workstation.toml").write_text('[score]\nprovider = "rerank"\nmodel = "another"\n')
    by_role = checks(client.get("/api/providers/health"))
    assert by_role["score"]["status"] == "unchecked"


def test_check_one_block(client: TestClient, runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "failed")
    before = checks(client.post("/api/providers/health/check"))
    monkeypatch.setenv("FAKE_DOCTOR", "ok")
    after = checks(client.post("/api/providers/health/check", json={"blocks": ["score"]}))
    assert json.loads((runs_dir / "doctor-argv.json").read_text())[-1] == "--block=score"
    assert after["score"]["status"] == "ok"
    assert after["score"]["checked_at"] != before["score"]["checked_at"]
    assert after["search"] == before["search"]


def test_check_all(client: TestClient) -> None:
    by_role = checks(client.post("/api/providers/health/check"))
    assert all(c["checked_at"] is not None for c in by_role.values() if c["status"] != "skipped")


def test_unknown_block(client: TestClient, runs_dir: Path) -> None:
    response = client.post("/api/providers/health/check", json={"blocks": ["scorer"]})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_block"
    assert not (runs_dir / "doctor-argv.json").exists()


def test_doctor_timeout(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    previous = checks(client.post("/api/providers/health/check"))
    monkeypatch.setenv("FAKE_DOCTOR", "hang")
    monkeypatch.setattr(meta, "DOCTOR_TIMEOUT", 0.5)
    response = client.post("/api/providers/health/check")
    assert response.status_code == 502
    assert response.json()["error"] == "health_unavailable"
    assert checks(client.get("/api/providers/health")) == previous


def test_unreadable_doctor_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "garbage")
    response = client.post("/api/providers/health/check")
    assert response.status_code == 502


def test_invalid_profile_400(client: TestClient) -> None:
    assert client.get("/api/providers/health", params={"profile": "nope"}).status_code == 400


def test_health_release_and_policy(client: TestClient) -> None:
    response = client.get("/api/providers/health", params={"profile": "low-vram"})
    assert response.json()["gpu_policy"] == "exclusive"
    assert checks(response)["prefilter"]["release"] == "llama-swap"


def test_depths_standard_values(client: TestClient) -> None:
    found = {d["name"]: d for d in client.get("/api/depths").json()}
    assert list(found) == ["quick", "standard", "deep", "exhaustive"]
    assert found["standard"]["values"] == {
        "sub_queries": 3,
        "results_per_query": 10,
        "max_pages": 40,
        "passages_per_query": 10,
        "context_tokens": "auto",
        "gap_context_tokens": 4000,
        "rounds": 1,
        "queries_per_round": 3,
        "words": None,
    }
    assert found["quick"]["values"]["words"] == 600
    assert (found["deep"]["values"]["rounds"], found["exhaustive"]["values"]["queries_per_round"]) == (3, 4)


def test_profile_limits(client: TestClient) -> None:
    found = {p["name"]: p for p in client.get("/api/profiles").json()}
    workstation = found["workstation"]
    assert workstation["context_window"] == 32768
    assert (workstation["prompt_reserve_tokens"], workstation["max_output_tokens"]) == (2000, 8192)


def test_domain_defaults_normalised(client: TestClient) -> None:
    assert client.put("/api/settings", json={"domains": {"block": ["*.Pinterest.com"]}}).status_code == 200
    assert client.get("/api/settings").json()["domains"] == {"allow": [], "block": ["pinterest.com"]}


def test_invalid_domain_default(client: TestClient, config_dir: Path) -> None:
    response = client.put("/api/settings", json={"domains": {"allow": ["https://gob.pe/"]}})
    assert response.status_code == 422
    assert "domains.allow" in response.json()["detail"]
    assert "https://gob.pe/" in response.json()["detail"]
    assert not (config_dir / "server-settings.json").exists()


def test_profile_domain_lists(client: TestClient, tmp_path: Path) -> None:
    profiles = tmp_path / "config" / "wosarcher" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "nixos.toml").write_text('[search]\nprovider = "searxng"\nblock_domains = ["facebook.com"]\n')
    found = {p["name"]: p for p in client.get("/api/profiles").json()}
    assert (found["nixos"]["block_domains"], found["nixos"]["allow_domains"]) == (["facebook.com"], None)
    assert found["workstation"]["block_domains"] is None

import json
from pathlib import Path
from typing import Any, Protocol

import httpx
import pytest
import respx
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


def test_default_format(client: TestClient, config_dir: Path) -> None:
    assert client.get("/api/settings").json()["writing"]["format"] == "report"
    body = client.get("/api/settings").json()
    body["writing"]["format"] = "answer"
    assert client.put("/api/settings", json=body).status_code == 200
    assert client.get("/api/settings").json()["writing"]["format"] == "answer"


def test_settings_without_format(client: TestClient, config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "server-settings.json").write_text(json.dumps({"writing": {"words": 800}}))
    writing = client.get("/api/settings").json()["writing"]
    assert (writing["words"], writing["format"]) == (800, "report")


def test_invalid_settings_unchanged(client: TestClient, config_dir: Path) -> None:
    body = client.get("/api/settings").json()
    body["writing"]["citation_marker"] = "footnote"
    response = client.put("/api/settings", json=body)
    assert response.status_code == 422
    assert "writing.citation_marker" in response.json()["detail"]
    assert not (config_dir / "server-settings.json").exists()
    assert client.get("/api/settings").json()["writing"]["citation_marker"] == "numeric"


def add(config_dir: Path, name: str, text: str) -> None:
    (config_dir / name).parent.mkdir(parents=True, exist_ok=True)
    (config_dir / name).write_text(text)


RERANK = 'provider = "rerank"\nbase_url = "http://r.test/v1"\nmodel = "bge"\n'
USE_RERANK = '[use]\nprefilter = "bm25"\nscore = "rerank"\n'


def test_profiles_active_marked(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "profiles/cloud.toml", USE_RERANK)
    store_profile("workstation", {"XDG_CONFIG_HOME": str(config_dir.parent)})
    profiles = client.get("/api/profiles").json()
    assert {p["name"]: p["active"] for p in profiles} == {"cloud": False, "workstation": True}
    assert {p["source"] for p in profiles} == {"user"}


def test_profile_descriptions_and_entries(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "profiles/nixos.toml", '[use]\nprefilter = "bm25"\n')
    add(config_dir, "profiles/home.toml", 'description = "Home lab."\n' + USE_RERANK + 'llm = "agents"\n')
    add(config_dir, "providers/score/rerank.toml", RERANK)
    found = {p["name"]: p for p in client.get("/api/profiles").json()}
    assert (found["nixos"]["description"], found["home"]["description"]) == ("", "Home lab.")
    assert found["home"]["use"] == {
        "search": "searxng",
        "fetch": "firecrawl",
        "prefilter": "bm25",
        "score": "rerank",
        "llm": "agents",
    }
    assert found["nixos"]["use"]["score"] is None
    assert "score" in found["nixos"]["error"]


def test_broken_profile(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "profiles/old.toml", '[score]\nbase_url = "http://x"\n')
    response = client.get("/api/profiles")
    assert response.status_code == 200
    assert "score.base_url" in {p["name"]: p for p in response.json()}["old"]["error"]


def test_profile_limits(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "profiles/workstation.toml", '[use]\nprefilter = "bm25"\n[select]\nmax_context_tokens = 12000\n')
    workstation = {p["name"]: p for p in client.get("/api/profiles").json()}["workstation"]
    assert (workstation["context_tokens"], workstation["prompt_reserve_tokens"]) == (12000, 2000)
    assert "context_window" not in workstation
    assert workstation["model"] is None


class Answer(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


def entries(response: Answer) -> dict[str, dict[str, Any]]:
    assert response.status_code == 200, response.text
    return {f"{e['block']}/{e['name']}": e for e in response.json()["entries"]}


def test_providers_route(client: TestClient, config_dir: Path, runs_dir: Path) -> None:
    llm = 'provider = "openai"\nmodel = "qwen3-14b"\n'
    llm += "[models.qwen3-14b]\ncontext_window = 32768\nmax_output_tokens = 8192\n"
    add(config_dir, "providers/llm/agents.toml", llm + "[models.gemma-3-12b]\n")
    found = entries(client.get("/api/providers"))
    assert not (runs_dir / "doctor-argv.json").exists()
    assert list(found) == [
        "search/searxng",
        "fetch/firecrawl",
        "prefilter/bm25",
        "prefilter/none",
        "score/bm25",
        "llm/agents",
    ]
    models = found["llm/agents"]["models"]
    assert [(m["id"], m["context_window"], m["max_output_tokens"]) for m in models] == [
        ("qwen3-14b", 32768, 8192),
        ("gemma-3-12b", None, None),
    ]
    assert {found["search/searxng"]["status"], found["score/bm25"]["status"]} == {"unchecked", "skipped"}


def test_broken_entry_listed(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "providers/score/old.toml", 'provider = "rerank"\ntop_k = 25\n')
    assert "top_k" in entries(client.get("/api/providers"))["score/old"]["error"]


def test_no_secrets(client: TestClient, config_dir: Path, tmp_path: Path) -> None:
    secret = tmp_path / "llm-key"
    secret.write_text("sk-file-secret\n")
    add(config_dir, "providers/llm/agents.toml", f'provider = "openai"\napi_key_file = "{secret}"\n')
    for path in ("/api/providers", "/api/profiles"):
        text = client.get(path).text
        assert "sk-file-secret" not in text
        assert path == "/api/profiles" or str(secret) not in text


def test_slow_provider(client: TestClient, runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "slow")
    entries(client.post("/api/providers/check"))
    assert "--all-entries" in json.loads((runs_dir / "doctor-argv.json").read_text())
    (runs_dir / "doctor-argv.json").unlink()
    search = entries(client.get("/api/providers"))["search/searxng"]
    assert not (runs_dir / "doctor-argv.json").exists()
    assert (search["status"], search["latency_ms"]) == ("degraded", 1840)
    assert search["checked_at"] is not None


def test_failed_probe_in_check(client: TestClient, config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    add(config_dir, "providers/score/rerank.toml", RERANK)
    monkeypatch.setenv("FAKE_DOCTOR", "failed")
    score = entries(client.post("/api/providers/check"))["score/rerank"]
    assert (score["status"], score["detail"], score["checked_at"] is not None) == ("down", "refused", True)
    assert entries(client.get("/api/providers"))["score/rerank"]["status"] == "down"


def test_entry_changed_since_the_check(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "providers/score/rerank.toml", RERANK)
    entries(client.post("/api/providers/check"))
    add(config_dir, "providers/score/rerank.toml", RERANK.replace("bge", "another"))
    assert entries(client.get("/api/providers"))["score/rerank"]["status"] == "unchecked"


def test_same_name_in_two_blocks(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "providers/prefilter/kw.toml", 'provider = "embeddings"\nbase_url = "http://e.test/v1"\n')
    add(config_dir, "providers/score/kw.toml", RERANK)
    found = entries(client.post("/api/providers/check", json={"entries": ["score/kw"]}))
    assert found["score/kw"]["status"] == "ok"
    assert found["prefilter/kw"]["status"] == "unchecked"


def test_check_one_entry(client: TestClient, config_dir: Path, runs_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    add(config_dir, "providers/score/jev-strict.toml", 'provider = "jev"\nbase_url = "http://j.test/v1"\n')
    before = entries(client.post("/api/providers/check"))
    after = entries(client.post("/api/providers/check", json={"entries": ["score/jev-strict"]}))
    assert json.loads((runs_dir / "doctor-argv.json").read_text())[-1] == "--entry=score=jev-strict"
    assert after["score/jev-strict"]["checked_at"] != before["score/jev-strict"]["checked_at"]
    assert after["search/searxng"] == before["search/searxng"]


def test_check_all(client: TestClient) -> None:
    found = entries(client.post("/api/providers/check"))
    assert all(e["checked_at"] is not None for e in found.values() if e["status"] != "skipped")


@pytest.mark.parametrize(("name", "named"), [("score/nope", "score/nope"), ("scorer/bm25", "scorer")])
def test_unknown_entry_or_block(client: TestClient, runs_dir: Path, name: str, named: str) -> None:
    response = client.post("/api/providers/check", json={"entries": [name]})
    assert response.status_code == 400
    assert named in response.json()["detail"]
    assert not (runs_dir / "doctor-argv.json").exists()


def test_doctor_timeout(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    previous = entries(client.post("/api/providers/check"))
    monkeypatch.setenv("FAKE_DOCTOR", "hang")
    monkeypatch.setattr(meta, "DOCTOR_TIMEOUT", 0.5)
    response = client.post("/api/providers/check")
    assert response.status_code == 502
    assert response.json()["error"] == "health_unavailable"
    assert entries(client.get("/api/providers")) == previous


def test_unreadable_doctor_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "garbage")
    assert client.post("/api/providers/check").status_code == 502


def test_policy_and_release(client: TestClient, config_dir: Path) -> None:
    add(
        config_dir,
        "providers/prefilter/embeddings.toml",
        'provider = "embeddings"\nrelease = "llama-swap"\nmodel = "e"\n',
    )
    add(config_dir, "profiles/workstation.toml", '[use]\nprefilter = "embeddings"\n[run]\ngpu_policy = "exclusive"\n')
    response = client.get("/api/providers")
    assert response.json()["gpu_policy"] == "exclusive"
    assert entries(response)["prefilter/embeddings"]["release"] == "llama-swap"


def test_depths_standard_values(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "depths/wide.toml", "[plan]\nmax_sub_queries = 10\n[write]\nwords = 1500\n")
    found = {d["name"]: d for d in client.get("/api/depths").json()}
    assert list(found) == ["quick", "standard", "deep", "exhaustive", "wide"]
    assert found["standard"]["source"] == "builtin"
    assert found["standard"]["values"] == {
        "sub_queries": 3,
        "results_per_query": 10,
        "max_pages": 40,
        "passages_per_query": 10,
        "rounds": 1,
        "queries_per_round": 3,
        "words": None,
    }
    assert found["quick"]["values"]["words"] == 600
    assert (found["deep"]["values"]["rounds"], found["exhaustive"]["values"]["queries_per_round"]) == (3, 4)
    wide = found["wide"]
    assert (wide["source"], wide["values"]["sub_queries"], wide["values"]["words"]) == ("user", 10, 1500)


def test_domain_defaults_normalised(client: TestClient) -> None:
    assert client.put("/api/settings", json={"domains": {"block": ["*.Pinterest.com"]}}).status_code == 200
    assert client.get("/api/settings").json()["domains"] == {"allow": [], "block": ["pinterest.com"]}


def test_invalid_domain_default(client: TestClient, config_dir: Path) -> None:
    response = client.put("/api/settings", json={"domains": {"allow": ["https://gob.pe/"]}})
    assert response.status_code == 422
    assert "domains.allow" in response.json()["detail"]
    assert "https://gob.pe/" in response.json()["detail"]
    assert not (config_dir / "server-settings.json").exists()


def test_profile_domain_lists(client: TestClient, config_dir: Path) -> None:
    add(config_dir, "profiles/nixos.toml", '[use]\nprefilter = "bm25"\n[search]\nblock_domains = ["facebook.com"]\n')
    found = {p["name"]: p for p in client.get("/api/profiles").json()}
    assert (found["nixos"]["block_domains"], found["nixos"]["allow_domains"]) == (["facebook.com"], None)
    assert found["workstation"]["block_domains"] is None


@respx.mock
def test_models_listed(client: TestClient) -> None:
    respx.get("http://llm.test/v1/models").respond(200, json={"data": [{"id": "a"}, {"id": "b"}]})
    assert client.get("/api/models?llm=agents").json() == {"models": ["a", "b"]}
    assert client.get("/api/models").json() == {"models": ["a", "b"]}


@respx.mock
def test_models_endpoint_down(client: TestClient) -> None:
    respx.get("http://llm.test/v1/models").mock(side_effect=httpx.ConnectError("refused"))
    response = client.get("/api/models?llm=agents")
    assert (response.status_code, response.json()) == (200, {"models": []})


def test_models_unknown_entry(client: TestClient) -> None:
    assert client.get("/api/models?llm=nope").status_code == 400

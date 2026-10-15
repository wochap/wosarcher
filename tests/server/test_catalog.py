"""Catalog runs through the server: create, draft, summaries, artifacts, and forks."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.server.conftest import BASE_URL, MakeApp, argv, create, finished
from tests.server.test_runs import on_disk
from tests.stages.catalog_data import structure, structure_data
from wosarcher.adapters.fakes import FakeLLM
from wosarcher.config import Settings
from wosarcher.http import UsageLedger
from wosarcher.models import CatalogRecord, Completion, Effort, Message, Node, RunRequest
from wosarcher.server.state import DraftLLM
from wosarcher.store import RunStore

BRIEF = "Every public organization of the Peruvian state"


def post(client: TestClient, request: dict[str, Any], path: str = "/api/runs") -> Any:
    return client.post(path, files=[("request", (None, json.dumps(request).encode()))])


def catalog_request(**changes: Any) -> dict[str, Any]:
    return {"query": BRIEF, "kind": "catalog", "structure": structure_data(), **changes}


def test_catalog_run(client: TestClient, runs_dir: Path) -> None:
    run_id = create(client, catalog_request(domains={"allow": ["gob.pe"]}))
    finished(client, run_id)
    record = json.loads((runs_dir / run_id / "request.json").read_text())
    assert record["request"]["kind"] == "catalog"
    assert record["request"]["structure"]["relation"] == "organismos adscritos"
    assert record["form"]["kind"] == "catalog"
    assert record["form"]["structure"]["seeds"][0]["name"] == "Poder Ejecutivo"
    args = argv(runs_dir, run_id)
    assert args[args.index("--kind") + 1] == "catalog"
    assert json.loads(args[args.index("--structure") + 1])["relation"] == "organismos adscritos"
    assert "write.tone" not in " ".join(args)
    events = [json.loads(line) for line in (runs_dir / run_id / "events.jsonl").read_text().splitlines()]
    stages = [event["stage"] for event in events if event["type"] == "stage.done"]
    assert stages[:2] == ["load", "draft"]


def test_no_structure_sends_none(client: TestClient, runs_dir: Path) -> None:
    response = post(client, {"query": BRIEF, "kind": "catalog"})
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    finished(client, run_id)
    args = argv(runs_dir, run_id)
    assert args[args.index("--kind") + 1] == "catalog"
    assert "--structure" not in args


@pytest.mark.parametrize(
    ("changes", "named"),
    [
        ({"writing": {"tone": "critical"}}, "writing"),
        ({"depth": "quick"}, "depth"),
        ({"research": {"rounds": 2}}, "research"),
        ({"sources": "files"}, "sources"),
        ({"until": "write"}, "until"),
    ],
)
def test_research_fields_on_catalog_422(client: TestClient, changes: dict[str, Any], named: str) -> None:
    response = post(client, catalog_request(**changes))
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith(f"{named}:")
    if named in ("writing", "depth", "research"):
        assert "catalog" in detail


def test_structure_on_research_422(client: TestClient) -> None:
    response = post(client, {"query": "q", "structure": structure_data()})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("structure:")
    assert "research" in response.json()["detail"]


def test_invalid_structure_names_seeds(client: TestClient, runs_dir: Path) -> None:
    seeds = [{"name": "X", "type": "planet"}]
    response = post(client, catalog_request(structure=structure_data(seeds=seeds)))
    assert response.status_code == 422
    assert "structure.seeds" in response.json()["detail"]
    assert not any(runs_dir.glob("2*"))


def test_structure_language_and_search_language_422(client: TestClient) -> None:
    response = post(client, catalog_request(structure=structure_data(language="es"), search_language="es-PE"))
    assert response.status_code == 422
    assert response.json()["detail"].startswith("search_language:")


def test_structure_language_invalid_422(client: TestClient) -> None:
    response = post(client, catalog_request(structure=structure_data(language="spanish")))
    assert response.status_code == 422
    assert "structure.language" in response.json()["detail"]


def test_catalog_summary(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "c", ends=False, request=RunRequest(query="q", kind="catalog", structure=structure()))
    store = RunStore(runs_dir, runs_dir)
    nodes = [Node(id=f"n{n}", name=f"N{n}", type="ministry", status="extracted") for n in range(72)]
    nodes.append(Node(id="todo", name="Todo", type="ministry"))
    store.write_text("c", "nodes.jsonl", "".join(node.model_dump_json() + "\n" for node in nodes))
    found = client.get("/api/runs/c").json()
    assert (found["kind"], found["nodes"], found["writing"]) == ("catalog", 72, None)
    records = [{"id": "a"}, {"id": "b"}]
    store.write_artifact("c", "catalog.json", CatalogRecord(records=records, nodes=73, reason="max nodes"))
    listed = next(run for run in client.get("/api/runs").json() if run["run_id"] == "c")
    assert listed["nodes"] == 2


def test_older_run_without_kind(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    path = runs_dir / "r" / "request.json"
    record = json.loads(path.read_text())
    record["request"].pop("kind", None)
    path.write_text(json.dumps(record))
    found = client.get("/api/runs/r").json()
    assert (found["kind"], found["nodes"]) == ("research", None)
    assert found["writing"] is not None


@pytest.mark.parametrize("name", ["structure.json", "nodes.jsonl", "records.jsonl", "catalog.json"])
def test_catalog_artifacts(client: TestClient, runs_dir: Path, name: str) -> None:
    on_disk(runs_dir, "c", ends=True, request=RunRequest(query="q", kind="catalog", structure=structure()))
    (runs_dir / "c" / name).write_text("{}\n")
    response = client.get(f"/api/runs/c/artifacts/{name}")
    assert response.status_code == 200
    expected = "application/x-ndjson" if name.endswith(".jsonl") else "application/json"
    assert response.headers["content-type"].startswith(expected)


def finished_catalog(client: TestClient) -> str:
    run_id = create(client, catalog_request())
    finished(client, run_id)
    return run_id


def test_fork_expand_more(client: TestClient, runs_dir: Path) -> None:
    parent = finished_catalog(client)
    response = client.post(f"/api/runs/{parent}/fork", json={"from": "expand", "limits": {"max_depth": 4}})
    assert response.status_code == 201, response.text
    child = response.json()["run_id"]
    finished(client, child)
    args = argv(runs_dir, child)
    assert args[args.index("--max-depth") + 1] == "4"
    record = json.loads((runs_dir / child / "request.json").read_text())
    assert record["request"]["structure"]["limits"]["max_depth"] == 4


def test_fork_lower_limit_422(client: TestClient) -> None:
    parent = finished_catalog(client)
    response = client.post(f"/api/runs/{parent}/fork", json={"from": "expand", "limits": {"max_nodes": 50}})
    assert response.status_code == 422
    assert "limits.max_nodes" in response.json()["detail"]


def test_fork_expand_needs_raised_limit(client: TestClient) -> None:
    parent = finished_catalog(client)
    response = client.post(f"/api/runs/{parent}/fork", json={"from": "expand", "limits": {"max_nodes": 200}})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("limits:")


def test_catalog_fork_from_write_422(client: TestClient) -> None:
    parent = finished_catalog(client)
    response = client.post(f"/api/runs/{parent}/fork", json={"from": "write"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "'expand'" in detail
    assert "'extract'" in detail


def test_catalog_fork_writing_422(client: TestClient) -> None:
    parent = finished_catalog(client)
    response = client.post(f"/api/runs/{parent}/fork", json={"from": "extract", "writing": {"tone": "critical"}})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("writing:")


def test_catalog_fork_from_extract(client: TestClient, runs_dir: Path) -> None:
    parent = finished_catalog(client)
    response = client.post(f"/api/runs/{parent}/fork", json={"from": "extract"})
    assert response.status_code == 201, response.text
    finished(client, response.json()["run_id"])
    assert "--max-depth" not in argv(runs_dir, response.json()["run_id"])


def test_research_fork_limits_422(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    response = client.post("/api/runs/r/fork", json={"from": "write", "limits": {"max_depth": 4}})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("limits:")


def test_research_fork_from_expand_422(client: TestClient, runs_dir: Path) -> None:
    on_disk(runs_dir, "r", ends=True)
    response = client.post("/api/runs/r/fork", json={"from": "expand"})
    assert response.status_code == 422
    assert "'select'" in response.json()["detail"]


# Draft route


def fixed(llm: Any) -> DraftLLM:
    """A draft LLM factory that always returns `llm`."""

    def make(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Any:
        return llm

    return make


def draft_client(make_app: MakeApp, llm: Any) -> TestClient:
    return TestClient(make_app(draft_llm=fixed(llm)), base_url=BASE_URL)


def test_draft_route(make_app: MakeApp, runs_dir: Path) -> None:
    llm = FakeLLM(["Here: " + json.dumps(structure_data())])
    notes = ("attachments", ("org.md", b"# Organigrama\n\nMinisterios del Peru\n"))
    with draft_client(make_app, llm) as client:
        fields = [("request", (None, json.dumps({"brief": BRIEF}).encode())), notes]
        response = client.post("/api/catalog/draft", files=fields)
        assert response.status_code == 200, response.text
        found = response.json()
        assert found["relation"] == "organismos adscritos"
        assert client.get("/api/runs").json() == []
        assert post(client, {"query": BRIEF, "kind": "catalog", "structure": found}).status_code == 201
    assert BRIEF in llm.calls[0][0].content
    assert "Organigrama" in llm.calls[0][1].content


class Down:
    async def complete(
        self, messages: list[Message], *, max_tokens: int, effort: Effort, temperature: float | None = None
    ) -> Completion:
        raise ConnectionError("connection refused")


def test_draft_failed(make_app: MakeApp, runs_dir: Path) -> None:
    with draft_client(make_app, Down()) as client:
        response = post(client, {"brief": BRIEF}, "/api/catalog/draft")
        assert response.status_code == 502
        assert response.json()["error"] == "draft_failed"
        assert "connection refused" in response.json()["detail"]
        assert client.get("/api/runs").json() == []


def test_draft_unreadable_reply(make_app: MakeApp) -> None:
    with draft_client(make_app, FakeLLM(["no json"])) as client:
        response = post(client, {"brief": BRIEF}, "/api/catalog/draft")
        assert (response.status_code, response.json()["error"]) == (502, "draft_failed")


def test_draft_empty_brief_422(make_app: MakeApp) -> None:
    with draft_client(make_app, FakeLLM()) as client:
        response = post(client, {"brief": "  "}, "/api/catalog/draft")
        assert response.status_code == 422
        assert response.json()["detail"].startswith("brief:")


def test_draft_needs_login(make_app: MakeApp, config_dir: Path, password_hash: str) -> None:
    from wosarcher.auth import AuthStore

    AuthStore(config_dir / "auth.json").set_password(password_hash)
    with draft_client(make_app, FakeLLM()) as client:
        response = post(client, {"brief": BRIEF}, "/api/catalog/draft")
        assert response.status_code == 401


def test_catalog_fork_thinking_maps_to_extract(client: TestClient, runs_dir: Path) -> None:
    parent = finished_catalog(client)
    body = {"from": "extract", "llm": {"reasoning": {"write": "high"}}}
    response = client.post(f"/api/runs/{parent}/fork", json=body)
    assert response.status_code == 201, response.text
    child = response.json()["run_id"]
    finished(client, child)
    args = argv(runs_dir, child)
    assert 'llm.reasoning.gap="high"' in args
    assert not any(arg.startswith("llm.reasoning.write") for arg in args)

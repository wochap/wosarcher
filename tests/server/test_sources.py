from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from wosarcher.models import (
    Candidate,
    Chunk,
    Context,
    Page,
    Passage,
    Plan,
    Query,
    RunRecord,
    RunRequest,
    Score,
    SelectSkip,
    Source,
)
from wosarcher.store import RunStore

WEB = Source(source_id="web1", kind="web", uri="https://example.org/a", title="A page")
FILE = Source(source_id="file1", kind="file", uri="notes.md", title="Notes")
QUERIES = [Query(id="q1", text="one"), Query(id="q2", text="two"), Query(id="q3", text="three")]
# Positions 2 and 3 were removed as near-duplicates.
POSITIONS = {"c0": 0, "c1": 1, "c4": 4, "c5": 5, "c6": 6}


def score(query_id: str, chunk_id: str, value: float, dropped: str | None = None) -> Score:
    kept = dropped is None
    return Score.model_validate(
        {"query_id": query_id, "chunk_id": chunk_id, "value": value, "scorer": "bm25", "display": value}
        | {"kept": kept, "dropped": dropped}
    )


def write_run(runs_dir: Path, run_id: str, scored: bool) -> None:
    """Page `web1` found by q1 and q2; q1 keeps its top 2."""
    store = RunStore(runs_dir, runs_dir)
    store.run_dir(run_id).mkdir(parents=True)
    settings: dict[str, Any] = {"score": {"provider": "bm25", "top_k": 2}, "select": {"max_chunks_per_source": 3}}
    created = datetime(2026, 1, 1, tzinfo=UTC)
    record = RunRecord(run_id=run_id, created_at=created, request=RunRequest(query="q"), profile="p", settings=settings)
    store.write_artifact(run_id, "request.json", record)
    store.write_artifact(run_id, "plan.json", Plan(queries=QUERIES))
    page = Page(source=WEB, text="text", truncated=True, rank=1, query_ids=["q1", "q2"])
    store.write_artifact(run_id, "pages.jsonl", [page])
    store.write_artifact(run_id, "files.jsonl", [Page(source=FILE, text="notes")])
    chunks = [Chunk(chunk_id=c, source_id="web1", position=p, text=c, heading_path=["H"]) for c, p in POSITIONS.items()]
    chunks.append(Chunk(chunk_id="f0", source_id="file1", position=0, text="f0"))
    store.write_artifact(run_id, "chunks.jsonl", chunks)
    pairs = [("q1", "c0"), ("q1", "c1"), ("q1", "c4"), ("q1", "c5"), ("q2", "c0")]
    pairs += [(q.id, "f0") for q in QUERIES]
    store.write_artifact(run_id, "candidates.jsonl", [Candidate(query_id=q, chunk_id=c) for q, c in pairs])
    if not scored:
        return
    scores = [
        score("q1", "c0", 0.9),
        score("q1", "c1", 0.8),
        score("q1", "c4", 0.7, "query_cap"),
        score("q1", "c5", 0.3, "threshold"),
        score("q2", "c0", 0.6, "other_query"),
        score("q1", "f0", 0.2, "threshold"),
        score("q2", "f0", 0.4, "threshold"),
        score("q3", "f0", 0.1, "threshold"),
    ]
    store.write_artifact(run_id, "scores.jsonl", scores)
    skip = SelectSkip(chunk_id="c1", query_id="q1", reason="budget", tokens_needed=410, tokens_left=120)
    store.write_artifact(run_id, "select.jsonl", [skip])
    passage = Passage(n=14, chunk_id="c0", source_id="web1", query_id="q1", text="c0", scorer="bm25", display=0.9)
    context = Context(query="q", passages=[passage], sources=[WEB], budget_tokens=500, used_tokens=380)
    store.write_artifact(run_id, "context.json", context)


def chunks_of(client: TestClient, run_id: str, source_id: str = "web1") -> dict[str, Any]:
    response = client.get(f"/api/runs/{run_id}/sources/{source_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_finished_run_fates(client: TestClient, runs_dir: Path) -> None:
    write_run(runs_dir, "r", scored=True)
    view = chunks_of(client, "r")
    assert (view["source"]["title"], view["truncated"], view["query_cap"], view["source_cap"]) == ("A page", True, 2, 3)
    assert view["threshold"] == 0.5
    assert [q["id"] for q in view["queries"]] == ["q1", "q2", "q3"]
    chunks = {chunk["chunk_id"]: chunk for chunk in view["chunks"]}
    assert list(chunks) == ["c0", "c1", "c4", "c5", "c6"]

    cited = chunks["c0"]["fate"]
    assert (cited["kind"], cited["n"], cited["query_id"], cited["rank"], cited["kept_in_query"]) == (
        "cited",
        14,
        "q1",
        1,
        2,
    )

    budget = chunks["c1"]["fate"]
    assert (budget["kind"], budget["tokens_needed"], budget["tokens_left"]) == ("budget", 410, 120)

    capped = chunks["c4"]["fate"]
    assert (capped["kind"], capped["display"], capped["rank"], capped["ranked"]) == ("query_cap", 0.7, 3, 3)
    assert chunks["c4"]["removed_before"] == 2
    assert chunks["c1"]["removed_before"] == 0

    states = {q["query_id"]: q["state"] for q in chunks["c0"]["queries"]}
    assert states == {"q1": "kept", "q2": "other_query", "q3": "not_in_results"}
    states = {q["query_id"]: q["state"] for q in chunks["c4"]["queries"]}
    assert states == {"q1": "query_cap", "q2": "prefiltered", "q3": "not_in_results"}

    assert chunks["c5"]["fate"]["kind"] == "below_threshold"
    assert chunks["c5"]["fate"]["rank"] is None
    assert chunks["c6"]["fate"] == {"kind": "prefiltered"} | {
        key: None
        for key in ("query_id", "display", "rank", "ranked", "kept_in_query", "n", "tokens_needed", "tokens_left")
    }


def test_file_source_pairs_every_query(client: TestClient, runs_dir: Path) -> None:
    write_run(runs_dir, "r", scored=True)
    view = chunks_of(client, "r", "file1")
    assert view["source"]["kind"] == "file"
    (chunk,) = view["chunks"]
    assert [q["state"] for q in chunk["queries"]] == ["below_threshold"] * 3
    assert (chunk["fate"]["kind"], chunk["fate"]["query_id"]) == ("below_threshold", "q2")


def test_running_run_is_pending(client: TestClient, runs_dir: Path) -> None:
    write_run(runs_dir, "r", scored=False)
    chunks = chunks_of(client, "r")["chunks"]
    assert {chunk["fate"]["kind"] for chunk in chunks} == {"pending", "prefiltered"}
    states = {q["query_id"]: q["state"] for q in chunks[0]["queries"]}
    assert states == {"q1": "pending", "q2": "pending", "q3": "not_in_results"}
    assert chunks_of(client, "r")["threshold"] is None


def test_unknown_run_and_source_404(client: TestClient, runs_dir: Path) -> None:
    write_run(runs_dir, "r", scored=True)
    response = client.get("/api/runs/nope/sources/web1")
    assert (response.status_code, response.json()["error"]) == (404, "run_not_found")
    response = client.get("/api/runs/r/sources/nope")
    assert (response.status_code, response.json()["error"]) == (404, "source_not_found")

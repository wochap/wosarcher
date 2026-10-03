import json

import httpx
import pytest
import respx

from tests.adapters.conftest import chunks, provider_client
from wosarcher.adapters.rerank import RerankScorer
from wosarcher.config import ScoreConfig
from wosarcher.http import ProviderError, UsageLedger
from wosarcher.models import Query

BASE = "http://desktop.lan:8001/v1"
Q2 = Query(id="q2", text="battery")


def scorer(http: httpx.AsyncClient, ledger: UsageLedger, **fields: object) -> RerankScorer:
    cfg = ScoreConfig.model_validate({"provider": "rerank", "base_url": BASE, **fields})
    return RerankScorer(cfg, provider_client(cfg, http, ledger), ledger)


def by_score(request: httpx.Request) -> httpx.Response:
    """Score each document by its number; results sorted best first, as servers do."""
    documents: list[str] = json.loads(request.content)["documents"]
    results = [{"index": i, "relevance_score": float(text.split()[-1])} for i, text in enumerate(documents)]
    return httpx.Response(200, json={"results": sorted(results, key=lambda r: -r["relevance_score"])})


@respx.mock
async def test_index_mapping_across_batches(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/rerank").mock(side_effect=by_score)
    items = chunks(*(f"doc {i}" for i in range(20)))
    scores = await scorer(http, ledger, batch_size=16).score(Q2, items)
    assert [score.value for score in scores] == [float(i) for i in range(20)]
    assert [score.chunk_id for score in scores] == [chunk.chunk_id for chunk in items]
    assert {(score.query_id, score.scorer) for score in scores} == {("q2", "rerank")}
    assert route.call_count == 2


@respx.mock
async def test_data_key_accepted(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/rerank").respond(200, json={"data": [{"index": 0, "relevance_score": 0.7}]})
    assert [score.value for score in await scorer(http, ledger).score(Q2, chunks("a"))] == [0.7]


@respx.mock
async def test_missing_document(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    results = [{"index": i, "relevance_score": 0.1} for i in range(3)]
    respx.post(f"{BASE}/rerank").respond(200, json={"results": results})
    with pytest.raises(ProviderError, match=r"^rerank: .*3 results for 4"):
        await scorer(http, ledger).score(Q2, chunks("a", "b", "c", "d"))


@respx.mock
async def test_empty_chunks_no_request(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    assert await scorer(http, ledger).score(Q2, []) == []
    assert respx.calls.call_count == 0


@respx.mock
async def test_usage_tokens_and_units(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    body = {
        "results": [{"index": 0, "relevance_score": 0.5}],
        "usage": {"total_tokens": 42},
        "meta": {"billed_units": {"search_units": 1}},
    }
    route = respx.post(f"{BASE}/rerank").respond(200, json=body)
    await scorer(http, ledger, model="reranker").score(Q2, chunks("a"))
    usage = ledger.totals[("rerank", "score")]
    assert (usage.input_tokens, usage.units) == (42, 1)
    assert json.loads(route.calls.last.request.content) == {"query": "battery", "documents": ["a"], "model": "reranker"}


async def test_not_calibrated(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    adapter = scorer(http, ledger)
    assert (adapter.name, adapter.calibrated) == ("rerank", False)


@respx.mock
async def test_probe_ok(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    body = {"model": "bge-reranker-v2-m3", "results": [{"index": 0, "relevance_score": 0.5}]}
    respx.post(f"{BASE}/rerank").respond(200, json=body)
    health = await scorer(http, ledger, model="reranker").probe()
    assert (health.block, health.status, health.model, health.unload) == ("score", "ok", "bge-reranker-v2-m3", "n/a")


@respx.mock
async def test_release_ollama_posts_keep_alive(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post("http://desktop.lan:8001/api/generate").respond(200, json={})
    await scorer(http, ledger, release="ollama", model="reranker").release()
    assert json.loads(route.calls.last.request.content) == {"model": "reranker", "keep_alive": 0}


async def probe_note(http: httpx.AsyncClient, ledger: UsageLedger, score: float, **fields: object) -> str | None:
    respx.post(f"{BASE}/rerank").respond(200, json={"results": [{"index": 0, "relevance_score": score}]})
    return (await scorer(http, ledger, **fields).probe()).note


@respx.mock
async def test_probe_note_logit(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    assert await probe_note(http, ledger, -3.25) == "probe score -3.25 (logit scale)"


@respx.mock
async def test_probe_note_probability(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    assert await probe_note(http, ledger, 0.93) == "probe score 0.93 (probability scale)"


@respx.mock
async def test_probe_note_configured_scale(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    assert await probe_note(http, ledger, 0.5, rerank_scale="logit") == "probe score 0.5 (logit scale)"

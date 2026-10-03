import asyncio
import base64
import json
import struct

import httpx
import pytest
import respx

from tests.adapters.conftest import provider_client
from wosarcher.adapters.embeddings import OpenAIEmbedder
from wosarcher.config import Provider
from wosarcher.http import ProviderError, UsageLedger

BASE = "http://desktop.lan:8002/v1"


def embedder(http: httpx.AsyncClient, ledger: UsageLedger, **fields: object) -> OpenAIEmbedder:
    cfg = Provider.model_validate({"provider": "embeddings", "base_url": BASE, **fields})
    return OpenAIEmbedder(cfg, provider_client(cfg, http, ledger), ledger)


def answer(request: httpx.Request, *, model: str = "m", tokens: int = 0) -> httpx.Response:
    texts: list[str] = json.loads(request.content)["input"]
    data = [{"index": i, "embedding": [float(len(text)), 1.0]} for i, text in enumerate(texts)]
    return httpx.Response(200, json={"model": model, "data": data, "usage": {"prompt_tokens": tokens}})


@respx.mock
async def test_order_restored(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    data = [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]
    respx.post(f"{BASE}/embeddings").respond(200, json={"data": data})
    assert await embedder(http, ledger).embed(["a", "b"]) == [[1.0], [2.0]]


@respx.mock
async def test_missing_vector(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    data = [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [2.0]}]
    respx.post(f"{BASE}/embeddings").respond(200, json={"data": data})
    with pytest.raises(ProviderError, match=r"embeddings: sent 3 texts but received 2"):
        await embedder(http, ledger).embed(["a", "b", "c"])


@respx.mock
async def test_two_batches(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    sizes: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sizes.append(len(json.loads(request.content)["input"]))
        return answer(request)

    respx.post(f"{BASE}/embeddings").mock(side_effect=handle)
    texts = ["x" * i for i in range(40)]
    vectors = await embedder(http, ledger, batch_size=32).embed(texts)
    assert sorted(sizes) == [8, 32]
    assert [vector[0] for vector in vectors] == [float(i) for i in range(40)]


@respx.mock
async def test_tokens_recorded(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    data = [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [1.0]}]
    respx.post(f"{BASE}/embeddings").mock(
        side_effect=[httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": t}}) for t in (300, 100)]
    )
    await embedder(http, ledger, batch_size=2).embed(["a"] * 4)
    usage = ledger.totals[("embeddings", "prefilter")]
    assert (usage.input_tokens, usage.requests) == (400, 2)


@respx.mock
async def test_base64_decoded(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    encoded = base64.b64encode(struct.pack("<2f", 0.5, -1.0)).decode()
    route = respx.post(f"{BASE}/embeddings").respond(200, json={"data": [{"index": 0, "embedding": encoded}]})
    assert await embedder(http, ledger).embed(["a"]) == [[0.5, -1.0]]
    assert json.loads(route.calls.last.request.content)["encoding_format"] == "base64"


@respx.mock
async def test_server_ignores_base64(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/embeddings").respond(200, json={"data": [{"index": 0, "embedding": [0.25, 2]}]})
    assert await embedder(http, ledger).embed(["a"]) == [[0.25, 2.0]]


@respx.mock
async def test_server_rejects_base64(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if "encoding_format" in json.loads(request.content):
            return httpx.Response(400, json={"error": "unknown encoding_format"})
        return answer(request)

    route = respx.post(f"{BASE}/embeddings").mock(side_effect=handle)
    adapter = embedder(http, ledger)
    assert await adapter.embed(["ab"]) == [[2.0, 1.0]]
    assert await adapter.embed(["abc"]) == [[3.0, 1.0]]
    assert route.call_count == 3


@respx.mock
async def test_reported_model_wins(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    data = [{"index": 0, "embedding": [0.0] * 1024}]
    respx.post(f"{BASE}/embeddings").respond(200, json={"model": "Qwen3-Embedding-0.6B", "data": data})
    info = await embedder(http, ledger, model="embed").describe()
    assert (info.model, info.dimension) == ("Qwen3-Embedding-0.6B", 1024)


@respx.mock
async def test_identity_learned_once(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/embeddings").mock(side_effect=answer)
    adapter = embedder(http, ledger)
    first, second = await asyncio.gather(adapter.describe(), adapter.describe())
    assert first == second
    assert route.call_count == 1


@respx.mock
async def test_probe_reports_model(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return answer(request, model="bge-m3")

    respx.post(f"{BASE}/embeddings").mock(side_effect=handle)
    health = await embedder(http, ledger, model="embed").probe()
    assert (health.block, health.status, health.model) == ("prefilter", "ok", "bge-m3")


@respx.mock
async def test_release_llama_swap(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.get("http://desktop.lan:8002/unload").respond(200)
    await embedder(http, ledger, release="llama-swap").release()
    assert route.call_count == 1

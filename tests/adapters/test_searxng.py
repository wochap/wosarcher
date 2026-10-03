import httpx
import pytest
import respx

from tests.adapters.conftest import provider_client
from wosarcher.adapters.searxng import SearxngSearcher
from wosarcher.config import SearchConfig
from wosarcher.http import ProviderError, UsageLedger
from wosarcher.models import Query

BASE = "http://searx.lan:8888"
Q1 = Query(id="q1", text="battery recycling")


def searcher(http: httpx.AsyncClient, ledger: UsageLedger, **fields: object) -> SearxngSearcher:
    cfg = SearchConfig.model_validate({"provider": "searxng", "base_url": BASE, **fields})
    return SearxngSearcher(cfg, provider_client(cfg, http, ledger), ledger)


def results(*urls: str | None) -> dict[str, object]:
    return {"results": [{"url": url, "title": f"t{i}", "content": f"c{i}"} for i, url in enumerate(urls)]}


@respx.mock
async def test_results_become_hits(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.get(f"{BASE}/search").respond(200, json=results("https://a.com", None, "https://b.com", "https://c.com"))
    hits = await searcher(http, ledger).search(Q1)
    assert [(hit.url, hit.rank, hit.query_ids) for hit in hits] == [
        ("https://a.com", 1, ["q1"]),
        ("https://b.com", 2, ["q1"]),
        ("https://c.com", 3, ["q1"]),
    ]
    assert (hits[0].title, hits[0].snippet) == ("t0", "c0")


@respx.mock
async def test_duplicate_urls(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.get(f"{BASE}/search").respond(200, json=results("https://a.com/x", "https://A.com/x/#top"))
    hits = await searcher(http, ledger).search(Q1)
    assert [hit.title for hit in hits] == ["t0"]


@respx.mock
async def test_no_results(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.get(f"{BASE}/search").respond(200, json={"results": []})
    assert await searcher(http, ledger).search(Q1) == []


@respx.mock
async def test_result_cap(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.get(f"{BASE}/search").respond(200, json=results(*(f"https://a.com/{i}" for i in range(20))))
    assert len(await searcher(http, ledger, max_results=5).search(Q1)) == 5


@respx.mock
async def test_language_and_time_range_sent(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.get(f"{BASE}/search").respond(200, json={"results": []})
    await searcher(http, ledger, language="de", time_range="month").search(Q1)
    params = route.calls.last.request.url.params
    assert (params["language"], params["time_range"]) == ("de", "month")
    assert (params["q"], params["format"], params["pageno"]) == ("battery recycling", "json", "1")


@respx.mock
async def test_defaults_omit_parameters(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.get(f"{BASE}/search").respond(200, json={"results": []})
    await searcher(http, ledger).search(Q1)
    params = route.calls.last.request.url.params
    assert "language" not in params
    assert "time_range" not in params


@respx.mock
async def test_forbidden_hint(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.get(f"{BASE}/search").respond(403)
    with pytest.raises(ProviderError, match=r"json.*search\.formats"):
        await searcher(http, ledger).search(Q1)


@respx.mock
async def test_request_counted(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.get(f"{BASE}/search").respond(200, json={"results": []})
    adapter = searcher(http, ledger)
    await adapter.search(Q1)
    await adapter.search(Q1)
    usage = ledger.totals[("searxng", "search")]
    assert (usage.requests, usage.input_tokens) == (2, 0)


@respx.mock
async def test_probe_ok(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.get(f"{BASE}/search").respond(200, json={"results": []})
    health = await searcher(http, ledger).probe()
    assert (health.block, health.status, health.unload) == ("search", "ok", "n/a")
    assert health.latency_ms is not None


@respx.mock
async def test_probe_failed(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.get(f"{BASE}/search").mock(side_effect=httpx.ConnectError("refused"))
    health = await searcher(http, ledger).probe()
    assert health.status == "failed"
    assert health.error is not None
    assert f"{BASE}/search" in health.error

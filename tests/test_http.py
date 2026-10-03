import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from pydantic import SecretStr

from wosarcher.config import Prices, Provider
from wosarcher.http import ProviderClient, ProviderError, UsageLedger

PRIMARY = "http://primary.lan:8001"
BACKUP = "http://backup.lan:8001"


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def client(http: httpx.AsyncClient, **fields: object) -> ProviderClient:
    cfg = Provider.model_validate({"provider": "rerank", "base_url": PRIMARY, **fields})
    return ProviderClient("rerank", cfg, http, UsageLedger({}), backoff=0)


@respx.mock
async def test_bearer_header_sent(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{PRIMARY}/rerank").respond(200, json={"ok": True})
    assert await client(http, api_key="sk-secret").post_json("/rerank", {}) == {"ok": True}
    assert route.calls.last.request.headers["authorization"] == "Bearer sk-secret"


@respx.mock
async def test_error_does_not_contain_key(http: httpx.AsyncClient) -> None:
    respx.post(f"{PRIMARY}/rerank").respond(401, text="bad key sk-secret")
    with pytest.raises(ProviderError) as error:
        await client(http, api_key=SecretStr("sk-secret")).post_json("/rerank", {})
    assert "sk-secret" not in str(error.value)
    assert "401" in str(error.value)


@respx.mock
async def test_rate_limited_then_success(http: httpx.AsyncClient) -> None:
    respx.post(f"{PRIMARY}/rerank").mock(side_effect=[httpx.Response(429), httpx.Response(200, json={"n": 1})])
    assert await client(http).post_json("/rerank", {}) == {"n": 1}


@respx.mock
async def test_client_error_not_retried(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{PRIMARY}/rerank").respond(400)
    with pytest.raises(ProviderError, match=r"rerank: HTTP 400"):
        await client(http).post_json("/rerank", {})
    assert route.call_count == 1


@respx.mock
async def test_retries_exhausted_after_four_attempts(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{PRIMARY}/rerank").respond(503, headers={"Retry-After": "0"})
    with pytest.raises(ProviderError, match="HTTP 503") as error:
        await client(http).post_json("/rerank", {})
    assert error.value.status == 503
    assert route.call_count == 4


@respx.mock
async def test_primary_down_uses_fallback(http: httpx.AsyncClient) -> None:
    primary = respx.post(f"{PRIMARY}/rerank").mock(side_effect=httpx.ConnectError("refused"))
    respx.post(f"{BACKUP}/rerank").respond(200, json={"from": "backup"})
    assert await client(http, fallback_urls=[BACKUP]).post_json("/rerank", {}) == {"from": "backup"}
    assert primary.call_count == 1


@respx.mock
async def test_primary_error_does_not_fall_back(http: httpx.AsyncClient) -> None:
    respx.post(f"{PRIMARY}/rerank").respond(400)
    backup = respx.post(f"{BACKUP}/rerank").respond(200, json={})
    with pytest.raises(ProviderError):
        await client(http, fallback_urls=[BACKUP]).post_json("/rerank", {})
    assert backup.call_count == 0


@respx.mock
async def test_all_endpoints_down_lists_every_url(http: httpx.AsyncClient) -> None:
    respx.post(f"{PRIMARY}/rerank").mock(side_effect=httpx.ConnectTimeout("timeout"))
    respx.post(f"{BACKUP}/rerank").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ProviderError) as error:
        await client(http, fallback_urls=[BACKUP]).post_json("/rerank", {})
    assert f"{PRIMARY}/rerank" in str(error.value)
    assert f"{BACKUP}/rerank" in str(error.value)


@respx.mock
async def test_concurrency_limit(http: httpx.AsyncClient) -> None:
    in_flight = 0
    peak = 0

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json={})

    respx.post(f"{PRIMARY}/rerank").mock(side_effect=slow)
    provider = client(http, concurrency=2)
    results = await asyncio.gather(*(provider.post_json("/rerank", {}) for _ in range(5)))
    assert len(results) == 5
    assert peak == 2


@respx.mock
async def test_cancel_releases_slot(http: httpx.AsyncClient) -> None:
    started = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/hang":
            started.set()
            await asyncio.sleep(3600)
        return httpx.Response(200, json={"ok": True})

    respx.route(host="primary.lan").mock(side_effect=hang)
    provider = client(http, concurrency=1)
    hanging = asyncio.create_task(provider.post_json("/hang", {}))
    await started.wait()
    waiting = asyncio.create_task(provider.post_json("/fast", {}))
    await asyncio.sleep(0.01)
    assert not waiting.done()
    hanging.cancel()
    assert await asyncio.wait_for(waiting, 1) == {"ok": True}
    assert hanging.cancelled()


def test_usage_summed() -> None:
    ledger = UsageLedger({})
    ledger.record("openai", "write", input_tokens=100)
    ledger.record("openai", "write", input_tokens=50, output_tokens=10)
    usage = ledger.totals[("openai", "write")]
    assert (usage.requests, usage.input_tokens, usage.output_tokens) == (2, 150, 10)


def test_no_price_means_zero_cost() -> None:
    ledger = UsageLedger({"firecrawl": Prices(per_unit=0.001)})
    ledger.record("rerank", "score", input_tokens=1000)
    ledger.record("firecrawl", "fetch", units=10)
    assert ledger.totals[("rerank", "score")].cost == 0
    assert ledger.totals[("rerank", "score")].input_tokens == 1000
    assert ledger.totals[("firecrawl", "fetch")].cost == pytest.approx(0.01)

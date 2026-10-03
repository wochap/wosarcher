import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx
from pydantic import SecretStr

from wosarcher.config import Prices, Provider
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, retry_delay, unload, unload_supported

PRIMARY = "http://primary.lan:8001"
BACKUP = "http://backup.lan:8001"


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def client(http: httpx.AsyncClient, *, backoff: float = 0, **fields: object) -> ProviderClient:
    cfg = Provider.model_validate({"provider": "rerank", "base_url": PRIMARY, **fields})
    return ProviderClient("rerank", cfg, http, UsageLedger({}), backoff=backoff)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    delays: list[float] = []

    async def record(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", record)
    return delays


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
async def test_retries_exhausted_after_eleven_attempts(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{PRIMARY}/rerank").respond(503)
    with pytest.raises(ProviderError, match="HTTP 503") as error:
        await client(http).post_json("/rerank", {})
    assert error.value.status == 503
    assert route.call_count == 11


@respx.mock
async def test_budget_stops_retries(http: httpx.AsyncClient, sleeps: list[float]) -> None:
    respx.post(f"{PRIMARY}/rerank").respond(503)
    with pytest.raises(ProviderError, match="HTTP 503"):
        await client(http, backoff=0.5, retry_budget=5).post_json("/rerank", {})
    assert sleeps == [0.5, 1, 2]


@respx.mock
async def test_retry_after_beyond_budget_fails_at_once(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{PRIMARY}/rerank").respond(429, headers={"Retry-After": "30"})
    with pytest.raises(ProviderError, match="HTTP 429"):
        await client(http, retry_budget=10).post_json("/rerank", {})
    assert route.call_count == 1


@respx.mock
async def test_zero_budget_no_retry(http: httpx.AsyncClient, sleeps: list[float]) -> None:
    route = respx.post(f"{PRIMARY}/rerank").respond(503)
    with pytest.raises(ProviderError, match="HTTP 503"):
        await client(http, backoff=0.5, retry_budget=0).post_json("/rerank", {})
    assert route.call_count == 1
    assert sleeps == []


@respx.mock
async def test_model_loading_then_ok(http: httpx.AsyncClient) -> None:
    respx.post(f"{PRIMARY}/rerank").mock(
        side_effect=[*[httpx.Response(503) for _ in range(4)], httpx.Response(200, json={"n": 1})]
    )
    assert await client(http).post_json("/rerank", {}) == {"n": 1}


def test_retry_delay_backoff_capped() -> None:
    response = httpx.Response(503)
    assert [retry_delay(response, attempt, 0.5) for attempt in range(6)] == [0.5, 1, 2, 4, 8, 8]


def test_retry_delay_header_seconds() -> None:
    assert retry_delay(httpx.Response(429, headers={"Retry-After": "7"}), 0, 0.5) == 7


def test_retry_delay_header_date() -> None:
    when = format_datetime(datetime.now(UTC) + timedelta(seconds=3), usegmt=True)
    assert 1.5 < retry_delay(httpx.Response(429, headers={"Retry-After": when}), 0, 0.5) <= 3


def test_retry_delay_header_past_date() -> None:
    when = format_datetime(datetime.now(UTC) - timedelta(seconds=30), usegmt=True)
    assert retry_delay(httpx.Response(429, headers={"Retry-After": when}), 0, 0.5) == 0


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


@respx.mock
async def test_get_json_params(http: httpx.AsyncClient) -> None:
    route = respx.get(f"{PRIMARY}/search").respond(200, json={"results": []})
    assert await client(http).get_json("/search", {"q": "x", "format": "json"}) == {"results": []}
    assert dict(route.calls.last.request.url.params) == {"q": "x", "format": "json"}


@respx.mock
async def test_root_path_strips_v1(http: httpx.AsyncClient) -> None:
    primary = respx.get("http://primary.lan:8001/running").mock(side_effect=httpx.ConnectError("refused"))
    backup = respx.get("http://backup.lan:8001/running").respond(200, json={})
    provider = client(http, base_url=f"{PRIMARY}/v1/", fallback_urls=[f"{BACKUP}/v1"])
    await provider.request("GET", "/running", root=True)
    assert (primary.call_count, backup.call_count) == (1, 1)


def sse(*events: str) -> bytes:
    return "".join(f"data: {event}\n\n" for event in events).encode()


@respx.mock
async def test_stream_lines_yields_data(http: httpx.AsyncClient) -> None:
    body = b": comment\n\n" + sse('{"a": 1}', "[DONE]")
    respx.post(f"{PRIMARY}/chat").respond(200, content=body)
    assert [line async for line in client(http).stream_lines("/chat", {})] == ['{"a": 1}', "[DONE]"]


@respx.mock
async def test_stream_retries_before_first_line(http: httpx.AsyncClient) -> None:
    route = respx.post(f"{PRIMARY}/chat").mock(side_effect=[httpx.Response(503), httpx.Response(200, content=sse("x"))])
    assert [line async for line in client(http).stream_lines("/chat", {})] == ["x"]
    assert route.call_count == 2


@respx.mock
async def test_stream_close_releases_slot(http: httpx.AsyncClient) -> None:
    respx.post(f"{PRIMARY}/chat").respond(200, content=sse("one", "two"))
    respx.post(f"{PRIMARY}/other").respond(200, json={"ok": True})
    provider = client(http, concurrency=1)
    lines = provider.stream_lines("/chat", {})
    assert await anext(lines) == "one"
    await lines.aclose()
    assert await asyncio.wait_for(provider.post_json("/other", {}), 1) == {"ok": True}


@respx.mock
async def test_unload_llama_swap_at_root(http: httpx.AsyncClient) -> None:
    route = respx.get("http://desktop.lan:8080/unload").respond(200)
    await unload(client(http, base_url="http://desktop.lan:8080/v1"), "llama-swap", "")
    assert route.call_count == 1


@respx.mock
async def test_unload_ollama_keep_alive(http: httpx.AsyncClient) -> None:
    route = respx.post("http://desktop.lan:11434/api/generate").respond(200, json={})
    await unload(client(http, base_url="http://desktop.lan:11434/v1"), "ollama", "qwen3:8b")
    assert json.loads(route.calls.last.request.content) == {"model": "qwen3:8b", "keep_alive": 0}


@respx.mock
async def test_unload_none_sends_nothing(http: httpx.AsyncClient) -> None:
    await unload(client(http), "none", "")
    assert respx.calls.call_count == 0


@respx.mock
async def test_unload_supported(http: httpx.AsyncClient) -> None:
    respx.get("http://ok.lan/running").respond(200, json=[])
    respx.get("http://plain.lan/running").respond(404)
    respx.get("http://down.lan/running").mock(side_effect=httpx.ConnectError("refused"))
    assert await unload_supported(client(http, base_url="http://ok.lan/v1"), "llama-swap")
    assert not await unload_supported(client(http, base_url="http://plain.lan/v1"), "llama-swap")
    assert not await unload_supported(client(http, base_url="http://down.lan/v1"), "llama-swap")

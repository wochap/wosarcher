import json

import httpx
import pytest
import respx

from tests.adapters.conftest import provider_client
from wosarcher.adapters.firecrawl import FirecrawlFetcher
from wosarcher.config import FetchConfig
from wosarcher.http import ProviderError, UsageLedger
from wosarcher.models import web_source_id

BASE = "http://crawl.lan:3002/v1"
URL = "https://example.org/battery"


def fetcher(http: httpx.AsyncClient, ledger: UsageLedger, **fields: object) -> FirecrawlFetcher:
    cfg = FetchConfig.model_validate({"provider": "firecrawl", "base_url": BASE, **fields})
    return FirecrawlFetcher(cfg, provider_client(cfg, http, ledger), ledger)


def scraped(markdown: str = "# Text", **metadata: object) -> dict[str, object]:
    return {"success": True, "data": {"markdown": markdown, "metadata": {"statusCode": 200, **metadata}}}


@respx.mock
async def test_page_fetched(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/scrape").respond(200, json=scraped("Body", title="Battery recycling"))
    page = await fetcher(http, ledger, api_key="fc-key").fetch(URL)
    assert (page.source.title, page.text) == ("Battery recycling", "Body")
    assert (page.source.uri, page.source.source_id, page.source.kind) == (URL, web_source_id(URL), "web")
    request = route.calls.last.request
    assert json.loads(request.content) == {
        "url": URL,
        "formats": ["markdown"],
        "onlyMainContent": True,
        "timeout": 45000,
    }
    assert request.headers["authorization"] == "Bearer fc-key"


@respx.mock
async def test_no_auth_header_without_key(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/scrape").respond(200, json=scraped())
    page = await fetcher(http, ledger).fetch(URL)
    assert "authorization" not in route.calls.last.request.headers
    assert page.source.title == URL


@respx.mock
async def test_pdf_markdown(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/scrape").respond(200, json=scraped("# Report\n\nPDF text"))
    page = await fetcher(http, ledger).fetch("https://example.org/report.pdf")
    assert page.text == "# Report\n\nPDF text"


@respx.mock
async def test_long_page_cut(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/scrape").respond(200, json=scraped("x" * 80000))
    page = await fetcher(http, ledger, max_chars=50000).fetch(URL)
    assert len(page.text) == 50000
    assert page.truncated


@respx.mock
async def test_target_not_found(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/scrape").respond(200, json=scraped(statusCode=404))
    with pytest.raises(ProviderError, match=rf"{URL}.*404"):
        await fetcher(http, ledger).fetch(URL)


@respx.mock
async def test_success_false(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/scrape").respond(200, json={"success": False, "error": "blocked"})
    with pytest.raises(ProviderError, match=rf"{URL}.*blocked"):
        await fetcher(http, ledger).fetch(URL)


@respx.mock
async def test_empty_page(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/scrape").respond(200, json=scraped(" \n\t "))
    with pytest.raises(ProviderError, match=rf"{URL}.*empty"):
        await fetcher(http, ledger).fetch(URL)


@respx.mock
async def test_credits_recorded(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/scrape").mock(
        side_effect=[httpx.Response(200, json=scraped(creditsUsed=1)), httpx.Response(200, json=scraped())]
    )
    adapter = fetcher(http, ledger)
    await adapter.fetch(URL)
    await adapter.fetch(URL)
    usage = ledger.totals[("firecrawl", "fetch")]
    assert (usage.requests, usage.units) == (2, 2)


@respx.mock
async def test_probe_ok(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/scrape").respond(200, json=scraped(title="Example Domain"))
    health = await fetcher(http, ledger).probe()
    assert (health.block, health.status, health.unload) == ("fetch", "ok", "n/a")
    assert json.loads(route.calls.last.request.content)["url"] == "https://example.com"


@respx.mock
async def test_release_sends_nothing(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    await fetcher(http, ledger, release="llama-swap").release()
    assert respx.calls.call_count == 0

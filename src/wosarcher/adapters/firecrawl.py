"""Fetcher: Firecrawl scrape (`POST <base_url>/scrape`) to markdown, self-hosted or cloud."""

from typing import Any

from wosarcher.config import FetchConfig
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, probe
from wosarcher.models import Page, ProviderHealth, Source, web_source_id

PROBE_URL = "https://example.com"


class FirecrawlFetcher:
    def __init__(self, cfg: FetchConfig, client: ProviderClient, ledger: UsageLedger, stage: str = "fetch") -> None:
        self.cfg = cfg
        self.client = client
        self.ledger = ledger
        self.stage = stage

    def fail(self, url: str, reason: str) -> ProviderError:
        return ProviderError(self.cfg.provider, f"cannot fetch {url}: {reason}", url=url)

    async def fetch(self, url: str) -> Page:
        body = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": self.cfg.only_main_content,
            "timeout": int(self.cfg.page_timeout * 1000),
        }
        data = await self.client.post_json("/scrape", body)
        page: dict[str, Any] = data.get("data") or {}
        metadata: dict[str, Any] = page.get("metadata") or {}
        self.ledger.record(self.cfg.provider, self.stage, units=float(metadata.get("creditsUsed") or 1))

        if not data.get("success"):
            raise self.fail(url, str(data.get("error") or "Firecrawl answered success: false"))
        status = metadata.get("statusCode")
        if isinstance(status, int) and status >= 400:
            raise self.fail(url, f"the page answered HTTP {status}")
        markdown = page.get("markdown") or ""
        if not markdown.strip():
            raise self.fail(url, "the page is empty")
        title = metadata.get("title")
        source = Source(
            source_id=web_source_id(url),
            kind="web",
            uri=url,
            title=title if isinstance(title, str) and title.strip() else url,
        )
        return Page(source=source, markdown=markdown[: self.cfg.max_chars])

    async def probe(self) -> ProviderHealth:
        async def call() -> None:
            await self.fetch(PROBE_URL)

        return await probe(self.client, "fetch", call)

    async def release(self) -> None:
        """Firecrawl serves no model; nothing to release."""

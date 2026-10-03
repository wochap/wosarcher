"""Searcher: a SearXNG instance's JSON API (`GET <base_url>/search`)."""

from typing import Any

from wosarcher.config import SearchConfig
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, probe
from wosarcher.models import Hit, ProviderHealth, Query, normalise_url

FORBIDDEN_HINT = "the instance must allow the json format: add `json` to `search.formats` in SearXNG's settings.yml"


class SearxngSearcher:
    def __init__(self, cfg: SearchConfig, client: ProviderClient, ledger: UsageLedger, stage: str = "search") -> None:
        self.cfg = cfg
        self.client = client
        self.ledger = ledger
        self.stage = stage

    async def search(self, query: Query) -> list[Hit]:
        params: dict[str, Any] = {"q": query.text, "format": "json", "pageno": 1}
        if self.cfg.language:
            params["language"] = self.cfg.language
        if self.cfg.time_range:
            params["time_range"] = self.cfg.time_range
        try:
            data = await self.client.get_json("/search", params)
        except ProviderError as error:
            if error.status != 403:
                raise
            raise ProviderError(self.cfg.provider, f"{error}; {FORBIDDEN_HINT}", url=error.url, status=403) from None
        self.ledger.record(self.cfg.provider, self.stage)

        hits: list[Hit] = []
        seen: set[str] = set()
        results: list[dict[str, Any]] = data.get("results") or []
        for result in results:
            url = result.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            key = normalise_url(url)
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                Hit(
                    url=url,
                    title=result.get("title") or url,
                    snippet=result.get("content") or "",
                    rank=len(hits) + 1,
                    query_ids=(query.query_id,),
                )
            )
            if len(hits) == self.cfg.max_results:
                break
        return hits

    async def probe(self) -> ProviderHealth:
        async def call() -> None:
            await self.search(Query(query_id="probe", text="test"))

        return await probe(self.client, "search", call)

    async def release(self) -> None:
        """SearXNG serves no model; nothing to release."""

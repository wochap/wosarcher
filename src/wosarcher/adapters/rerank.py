"""Scorer: a Cohere/Jina-style reranker (`POST <base_url>/rerank`). Scores are uncalibrated."""

import asyncio
from contextlib import suppress
from typing import Any

from wosarcher.config import ScoreConfig
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, probe, unload
from wosarcher.models import Chunk, ProviderHealth, Query, Score


class RerankScorer:
    name = "rerank"
    calibrated = False

    def __init__(self, cfg: ScoreConfig, client: ProviderClient, ledger: UsageLedger, stage: str = "score") -> None:
        self.cfg = cfg
        self.client = client
        self.ledger = ledger
        self.stage = stage

    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
        size = self.cfg.batch_size
        batches = [chunks[start : start + size] for start in range(0, len(chunks), size)]
        results = await asyncio.gather(*(self._batch(query.text, batch) for batch in batches))
        values = [value for result in results for value in result]
        return [
            Score(query_id=query.id, chunk_id=chunk.chunk_id, value=value, scorer=self.name)
            for chunk, value in zip(chunks, values, strict=True)
        ]

    async def _request(self, query: str, documents: list[str]) -> Any:
        body: dict[str, Any] = {"query": query, "documents": documents}
        if self.cfg.model:
            body["model"] = self.cfg.model
        data = await self.client.post_json("/rerank", body)
        usage: dict[str, Any] = data.get("usage") or {}
        meta: dict[str, Any] = data.get("meta") or {}
        billed: dict[str, Any] = meta.get("billed_units") or {}
        self.ledger.record(
            self.cfg.provider,
            self.stage,
            input_tokens=int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0),
            units=float(billed.get("search_units") or 0),
        )
        return data

    async def _batch(self, query: str, chunks: list[Chunk]) -> list[float]:
        data = await self._request(query, [chunk.text for chunk in chunks])
        results: list[dict[str, Any]] = data.get("results") or data.get("data") or []
        try:
            values = {int(result["index"]): float(result["relevance_score"]) for result in results}
        except (KeyError, TypeError, ValueError):
            raise ProviderError(self.cfg.provider, "rerank results need `index` and `relevance_score`") from None
        if len(results) != len(chunks) or set(values) != set(range(len(chunks))):
            raise ProviderError(
                self.cfg.provider, f"rerank answered {len(results)} results for {len(chunks)} documents"
            )
        return [values[index] for index in range(len(chunks))]

    async def probe(self) -> ProviderHealth:
        values: list[float] = []

        async def call() -> str | None:
            data = await self._request("probe", ["probe document"])
            results: list[dict[str, Any]] = data.get("results") or data.get("data") or []
            with suppress(KeyError, IndexError, TypeError, ValueError):
                values.append(float(results[0]["relevance_score"]))
            return data.get("model")

        health = await probe(self.client, "score", call)
        if health.status != "ok" or not values:
            return health
        return health.model_copy(update={"note": f"probe score {values[0]:g} ({self.scale(values[0])} scale)"})

    def scale(self, value: float) -> str:
        """The configured scale, or for `auto` the one this raw score implies."""
        if self.cfg.rerank_scale != "auto":
            return self.cfg.rerank_scale
        return "probability" if 0 <= value <= 1 else "logit"

    async def release(self) -> None:
        await unload(self.client, self.cfg.release, self.cfg.model)

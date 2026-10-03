"""Embedder: an OpenAI-compatible endpoint (`POST <base_url>/embeddings`), batched, base64 when supported."""

import asyncio
import base64
import sys
from array import array
from typing import Any

from wosarcher.config import Provider
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, probe, unload
from wosarcher.models import EmbedderInfo, ProviderHealth


class OpenAIEmbedder:
    def __init__(self, cfg: Provider, client: ProviderClient, ledger: UsageLedger, stage: str = "prefilter") -> None:
        self.cfg = cfg
        self.client = client
        self.ledger = ledger
        self.stage = stage
        self._base64 = True
        self._info: EmbedderInfo | None = None
        self._lock = asyncio.Lock()

    def fail(self, message: str) -> ProviderError:
        return ProviderError(self.cfg.provider, message)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        size = self.cfg.batch_size
        batches = [texts[start : start + size] for start in range(0, len(texts), size)]
        results = await asyncio.gather(*(self._batch(batch) for batch in batches))
        vectors = [vector for result in results for vector in result]
        if len({len(vector) for vector in vectors}) > 1:
            raise self.fail(f"vectors of different lengths: {sorted({len(vector) for vector in vectors})}")
        return vectors

    async def _batch(self, texts: list[str]) -> list[list[float]]:
        body: dict[str, Any] = {"input": texts}
        if self.cfg.model:
            body["model"] = self.cfg.model
        use_base64 = self._base64
        if use_base64:
            body["encoding_format"] = "base64"
        try:
            data = await self.client.post_json("/embeddings", body)
        except ProviderError as error:
            if not use_base64 or error.status not in (400, 422):
                raise
            self._base64 = False
            del body["encoding_format"]
            data = await self.client.post_json("/embeddings", body)
        usage: dict[str, Any] = data.get("usage") or {}
        self.ledger.record(self.cfg.provider, self.stage, input_tokens=int(usage.get("prompt_tokens") or 0))

        items: list[dict[str, Any]] = sorted(data.get("data") or [], key=lambda item: int(item.get("index", 0)))
        if len(items) != len(texts):
            raise self.fail(f"sent {len(texts)} texts but received {len(items)} embeddings")
        vectors = [self._decode(item.get("embedding")) for item in items]
        if self._info is None and vectors:
            model = data.get("model") or self.cfg.model or self.cfg.base_url
            self._info = EmbedderInfo(model=str(model), dimension=len(vectors[0]))
        return vectors

    def _decode(self, value: Any) -> list[float]:
        if isinstance(value, str):
            floats = array("f", base64.b64decode(value))
            if sys.byteorder == "big":
                floats.byteswap()
            return floats.tolist()
        if isinstance(value, list):
            return [float(number) for number in value]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        raise self.fail(f"embedding is neither base64 nor a list of numbers: {type(value).__name__}")

    async def describe(self) -> EmbedderInfo:
        """The model and dimension, learned from one short embedding when nothing was embedded yet."""
        async with self._lock:
            if self._info is None:
                await self.embed(["wosarcher"])
        if self._info is None:
            raise self.fail("the endpoint returned no embedding")
        return self._info

    async def probe(self) -> ProviderHealth:
        async def call() -> str:
            await self.embed(["wosarcher probe"])
            return (await self.describe()).model

        return await probe(self.client, "prefilter", call)

    async def release(self) -> None:
        await unload(self.client, self.cfg.release, self.cfg.model)

"""Scorer: TypeSafe Jev (`POST <base_url>/systemone`), a calibrated 0-3 usefulness score per chunk."""

import asyncio
import tomllib
from importlib.resources import files
from string import Template
from typing import Any

from wosarcher.config import ScoreConfig
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, probe, unload
from wosarcher.models import Chunk, ProviderHealth, Query, Score

DEFAULT_MODEL = "jev-latest"


def load_prompt() -> dict[str, Any]:
    return tomllib.loads(files("wosarcher").joinpath("prompts", "jev.toml").read_text(encoding="utf-8"))


class JevScorer:
    name = "jev"
    calibrated = True

    def __init__(self, cfg: ScoreConfig, client: ProviderClient, ledger: UsageLedger, stage: str = "score") -> None:
        self.cfg = cfg
        self.client = client
        self.ledger = ledger
        self.stage = stage
        prompt = load_prompt()
        self.instructions = Template(prompt["instructions"])
        self.criteria: list[str] = prompt["criteria"]

    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
        instructions = self.instructions.safe_substitute(query=query.text)
        values = await asyncio.gather(*(self._one(instructions, chunk.text) for chunk in chunks))
        return [
            Score(query_id=query.id, chunk_id=chunk.chunk_id, value=value, scorer=self.name)
            for chunk, value in zip(chunks, values, strict=True)
        ]

    async def _one(self, instructions: str, text: str) -> float:
        body = {
            "state": text,
            "model": self.cfg.model or DEFAULT_MODEL,
            "questions": {"usefulness": {"type": "score", "instructions": instructions, "criteria": self.criteria}},
        }
        data = await self.client.post_json("/systemone", body)
        usage: dict[str, Any] = data.get("usage") or {}
        self.ledger.record(self.cfg.provider, self.stage, input_tokens=int(usage.get("input_tokens") or 0))
        try:
            value = float(data["answers"]["usefulness"]["score"])
        except (KeyError, TypeError, ValueError):
            raise ProviderError(self.cfg.provider, "answer has no `answers.usefulness.score`") from None
        if not 0 <= value <= 3:
            raise ProviderError(self.cfg.provider, f"usefulness score {value} is outside 0 to 3")
        return value

    async def probe(self) -> ProviderHealth:
        async def call() -> str:
            await self._one(self.instructions.safe_substitute(query="probe"), "probe passage")
            return self.cfg.model or DEFAULT_MODEL

        return await probe(self.client, "score", call)

    async def release(self) -> None:
        if self.cfg.release != "none":
            await unload(self.client, self.cfg.release, self.cfg.model)

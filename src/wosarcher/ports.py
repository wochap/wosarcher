"""Protocols that stages depend on; adapters and fakes satisfy them structurally."""

from collections.abc import AsyncIterator
from typing import Protocol

from wosarcher.models import Chunk, Completion, Hit, Message, Page, Query, Score


class Searcher(Protocol):
    async def search(self, query: Query) -> list[Hit]: ...


class Fetcher(Protocol):
    async def fetch(self, url: str) -> Page: ...


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class Scorer(Protocol):
    name: str
    calibrated: bool

    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]: ...


class LLM(Protocol):
    async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion: ...

    def stream(self, messages: list[Message], *, max_tokens: int) -> AsyncIterator[str]: ...

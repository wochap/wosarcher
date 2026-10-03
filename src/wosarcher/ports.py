"""Protocols that stages depend on; adapters and fakes satisfy them structurally."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from wosarcher.models import Chunk, Completion, EmbedderInfo, Hit, Message, Page, ProviderHealth, Query, Score


class Searcher(Protocol):
    async def search(self, query: Query) -> list[Hit]: ...


class Fetcher(Protocol):
    async def fetch(self, url: str) -> Page: ...


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def describe(self) -> EmbedderInfo: ...


class Scorer(Protocol):
    name: str
    calibrated: bool

    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]: ...


class LLM(Protocol):
    async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion: ...

    def stream(self, messages: list[Message], *, max_tokens: int) -> AsyncIterator[str]: ...


class Managed(Protocol):
    """A remote adapter: health probe and model release."""

    async def probe(self) -> ProviderHealth: ...

    async def release(self) -> None: ...


@dataclass(frozen=True)
class Adapters:
    """Every port a run needs, built from settings by `build.build`."""

    searcher: Searcher
    fetcher: Fetcher
    embedder: Embedder | None
    scorers: dict[str, Scorer]
    planner: LLM
    writer: LLM
    managed: dict[str, Managed]

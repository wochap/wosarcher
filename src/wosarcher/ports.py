"""Protocols that stages depend on; adapters and fakes satisfy them structurally."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Protocol

from wosarcher.models import (
    Chunk,
    Completion,
    EmbedderInfo,
    ExportFormat,
    Hit,
    Message,
    Page,
    ProviderHealth,
    Query,
    Score,
)


class Searcher(Protocol):
    async def search(self, query: Query, page: int = 1) -> list[Hit]:
        """Every hit of one result page, ranked from 1 within the page."""
        ...


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

    def stream(
        self, messages: list[Message], *, max_tokens: int, on_finish: Callable[[str | None], None] = ...
    ) -> AsyncIterator[str]:
        """Text deltas in order; `on_finish` gets the final finish reason (or None) when the stream ends."""
        ...


class Managed(Protocol):
    """A remote adapter: health probe and model release."""

    async def probe(self) -> ProviderHealth: ...

    async def release(self) -> None: ...


class ExportError(Exception):
    """A conversion that failed or timed out; the message is the converter's last error line."""


class Exporter(Protocol):
    """Turns export Markdown into a document."""

    async def export(self, markdown: str, fmt: ExportFormat) -> bytes: ...

    def missing(self, fmt: ExportFormat) -> list[str]:
        """The programs `fmt` needs that are not installed."""
        ...


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

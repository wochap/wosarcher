"""Minimal fakes for every port; basedpyright checks them against the Protocols."""

from collections.abc import AsyncIterator

from wosarcher.models import Chunk, Completion, Hit, Message, Page, Query, Score, Source, web_source_id
from wosarcher.ports import LLM, Embedder, Fetcher, Scorer, Searcher


class FakeSearcher:
    async def search(self, query: Query) -> list[Hit]:
        return [Hit(url="https://example.com/a", title=query.text, query_ids=(query.query_id,))]


class FakeFetcher:
    async def fetch(self, url: str) -> Page:
        source = Source(source_id=web_source_id(url), kind="web", uri=url, title=url)
        return Page(source=source, markdown="# Title\n\ntext")


class FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]


class FakeScorer:
    name = "fake"
    calibrated = False

    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
        return [Score(query_id=query.query_id, chunk_id=c.chunk_id, value=1.0, scorer=self.name) for c in chunks]


class FakeLLM:
    async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion:
        return Completion(text=messages[-1].content[:max_tokens])

    async def stream(self, messages: list[Message], *, max_tokens: int) -> AsyncIterator[str]:
        yield messages[-1].content[:max_tokens]


searcher: Searcher = FakeSearcher()
fetcher: Fetcher = FakeFetcher()
embedder: Embedder = FakeEmbedder()
scorer: Scorer = FakeScorer()
llm: LLM = FakeLLM()

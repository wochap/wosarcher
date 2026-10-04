"""In-memory fakes for every port, for stage and runner tests. No network code."""

from collections.abc import AsyncIterator, Callable, Mapping
from hashlib import sha256

from wosarcher.models import (
    Chunk,
    Completion,
    EmbedderInfo,
    Hit,
    Message,
    Page,
    ProviderHealth,
    Query,
    Score,
    Source,
    web_source_id,
)

FAKE_DIMENSION = 8


def ignore(_reason: str | None) -> None:
    pass


def healthy(block: str, provider: str, model: str | None = None) -> ProviderHealth:
    return ProviderHealth(block=block, provider=provider, status="ok", model=model, latency_ms=0.0)


class FakeManaged:
    """Probe and release for every fake: `health` is returned, releases are counted."""

    def __init__(self, health: ProviderHealth) -> None:
        self.health = health
        self.releases = 0

    async def probe(self) -> ProviderHealth:
        return self.health

    async def release(self) -> None:
        self.releases += 1


class FakeSearcher(FakeManaged):
    def __init__(self, hits: Mapping[str, list[str]] | None = None) -> None:
        super().__init__(healthy("search", "fake"))
        self.hits = dict(hits or {})
        self.calls: list[Query] = []

    async def search(self, query: Query) -> list[Hit]:
        self.calls.append(query)
        return [
            Hit(url=url, title=url, snippet="", rank=rank, query_ids=[query.id])
            for rank, url in enumerate(self.hits.get(query.text, []), start=1)
        ]


class FakeFetcher(FakeManaged):
    def __init__(self, pages: Mapping[str, str] | None = None, failing: set[str] | None = None) -> None:
        super().__init__(healthy("fetch", "fake"))
        self.pages = dict(pages or {})
        self.failing = set(failing or ())
        self.calls: list[str] = []

    async def fetch(self, url: str) -> Page:
        self.calls.append(url)
        if url in self.failing or url not in self.pages:
            raise RuntimeError(f"fake: cannot fetch {url}")
        source = Source(source_id=web_source_id(url), kind="web", uri=url, title=url)
        return Page(source=source, text=self.pages[url])


class FakeEmbedder(FakeManaged):
    def __init__(self) -> None:
        super().__init__(healthy("prefilter", "fake", "fake-embed"))
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[byte / 255 for byte in sha256(text.encode()).digest()[:FAKE_DIMENSION]] for text in texts]

    async def describe(self) -> EmbedderInfo:
        return EmbedderInfo(model="fake-embed", dimension=FAKE_DIMENSION)


class FakeScorer(FakeManaged):
    def __init__(
        self,
        name: str = "fake",
        *,
        calibrated: bool = False,
        values: Mapping[str, float] | None = None,
        default: float = 1.0,
    ) -> None:
        super().__init__(healthy("score", name))
        self.name = name
        self.calibrated = calibrated
        self.values = dict(values or {})
        self.default = default
        self.calls: list[tuple[Query, list[Chunk]]] = []

    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
        self.calls.append((query, list(chunks)))
        return [
            Score(
                query_id=query.id,
                chunk_id=chunk.chunk_id,
                value=self.values.get(chunk.chunk_id, self.default),
                scorer=self.name,
            )
            for chunk in chunks
        ]


class FakeLLM(FakeManaged):
    """Replies in order; the last reply repeats when the script runs out."""

    def __init__(self, replies: list[str] | None = None) -> None:
        super().__init__(healthy("llm", "fake", "fake-llm"))
        self.replies = list(replies or ["ok"])
        self.calls: list[list[Message]] = []
        self.finish_reasons: list[str | None] = ["stop"]
        """One per stream call; the last one repeats."""

    def _next(self, messages: list[Message]) -> str:
        self.calls.append(list(messages))
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]

    async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion:
        return Completion(text=self._next(messages))

    async def stream(
        self, messages: list[Message], *, max_tokens: int, on_finish: Callable[[str | None], None] = ignore
    ) -> AsyncIterator[str]:
        words = self._next(messages).split(" ")
        for position, word in enumerate(words):
            yield word if position == len(words) - 1 else word + " "
        reasons = self.finish_reasons
        on_finish(reasons.pop(0) if len(reasons) > 1 else reasons[0])

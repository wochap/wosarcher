"""In-memory fakes for every port, for stage and runner tests. No network code."""

from collections.abc import AsyncIterator, Callable, Mapping
from hashlib import sha256

from wosarcher.models import (
    Chunk,
    Completion,
    Effort,
    EmbedderInfo,
    ExportFormat,
    Hit,
    Message,
    Page,
    ProviderHealth,
    Query,
    RunFinished,
    Score,
    Source,
    web_source_id,
)
from wosarcher.ports import ExportError

FAKE_DIMENSION = 8
FAKE_EXPORTS: dict[ExportFormat, bytes] = {"pdf": b"%PDF-fake", "docx": b"PK-fake-docx"}


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
    """`hits`: page 1 per query text; `pages`: every page per query text; `failing`: (text, page) pairs that raise."""

    def __init__(
        self,
        hits: Mapping[str, list[str]] | None = None,
        *,
        pages: Mapping[str, list[list[str]]] | None = None,
        failing: set[tuple[str, int]] | None = None,
    ) -> None:
        super().__init__(healthy("search", "fake"))
        self.pages = {text: [urls] for text, urls in (hits or {}).items()} | dict(pages or {})
        self.failing = set(failing or ())
        self.calls: list[Query] = []
        self.requests: list[tuple[str, int]] = []

    async def search(self, query: Query, page: int = 1) -> list[Hit]:
        if page == 1:
            self.calls.append(query)
        self.requests.append((query.text, page))
        if (query.text, page) in self.failing:
            raise RuntimeError(f"fake: page {page} of {query.text} failed")
        found = self.pages.get(query.text, [])
        urls = found[page - 1] if page <= len(found) else []
        return [
            Hit(url=url, title=url, snippet="", rank=rank, query_ids=[query.id]) for rank, url in enumerate(urls, 1)
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
        self.efforts: list[Effort] = []
        """The effort of each call, in call order."""
        self.temperatures: list[float | None] = []
        """The temperature of each call, in call order."""
        self.finish_reasons: list[str | None] = ["stop"]
        """One per stream call; the last one repeats."""

    def _next(self, messages: list[Message], effort: Effort, temperature: float | None) -> str:
        self.calls.append(list(messages))
        self.efforts.append(effort)
        self.temperatures.append(temperature)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]

    async def complete(
        self, messages: list[Message], *, max_tokens: int, effort: Effort, temperature: float | None = None
    ) -> Completion:
        return Completion(text=self._next(messages, effort, temperature))

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int,
        effort: Effort,
        temperature: float | None = None,
        on_finish: Callable[[str | None], None] = ignore,
    ) -> AsyncIterator[str]:
        words = self._next(messages, effort, temperature).split(" ")
        for position, word in enumerate(words):
            yield word if position == len(words) - 1 else word + " "
        reasons = self.finish_reasons
        on_finish(reasons.pop(0) if len(reasons) > 1 else reasons[0])


class FakeExporter:
    """Fixed bytes per format; records each Markdown it was given. `missing` and `failure` simulate errors."""

    def __init__(self, missing: Mapping[ExportFormat, list[str]] | None = None, failure: str | None = None) -> None:
        self.absent = dict(missing or {})
        self.failure = failure
        self.inputs: list[tuple[str, ExportFormat]] = []

    def missing(self, fmt: ExportFormat) -> list[str]:
        return self.absent.get(fmt, [])

    async def export(self, markdown: str, fmt: ExportFormat) -> bytes:
        self.inputs.append((markdown, fmt))
        if self.failure is not None:
            raise ExportError(self.failure)
        return FAKE_EXPORTS[fmt]


class FakeHook:
    """Records every `RunFinished` it gets; raises `error` after recording when one is set."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.fired: list[RunFinished] = []

    async def fire(self, finished: RunFinished) -> None:
        self.fired.append(finished)
        if self.error is not None:
            raise self.error

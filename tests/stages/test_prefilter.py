from pathlib import Path

import pytest

from wosarcher.adapters.fakes import FakeEmbedder
from wosarcher.models import Chunk, EmbedderInfo, Page
from wosarcher.runner.caches import EmbeddingMapping
from wosarcher.stages.chunk import scoring_text
from wosarcher.stages.prefilter import Pairing, pairs, prefilter, text_key
from wosarcher.store.caches import EmbeddingCache

from .ranking_data import chunks_of, file_page, queries, web_page


def test_web_chunks_pair_with_every_query() -> None:
    page = web_page("https://a.example", ["q1"])
    chunks = chunks_of(page, ["one", "two"])
    paired = pairs(queries(4), [page], chunks, "all")
    assert paired == {"q0": chunks, "q1": chunks, "q2": chunks, "q3": chunks}


def test_web_chunks_pair_with_finding_queries_only() -> None:
    page = web_page("https://a.example", ["q1", "q3"])
    chunks = chunks_of(page, ["one", "two"])
    paired = pairs(queries(4), [page], chunks, "found")
    assert {query_id for query_id, found in paired.items() if found} == {"q1", "q3"}
    assert paired["q1"] == chunks


@pytest.mark.parametrize("pairing", ["all", "found"])
def test_file_chunk_pairs_with_every_query(pairing: Pairing) -> None:
    page = file_page("notes.md")
    chunks = chunks_of(page, ["only"])
    paired = pairs(queries(3), [page], chunks, pairing)
    assert paired == {"q0": chunks, "q1": chunks, "q2": chunks}


async def test_small_input_is_passthrough() -> None:
    small = web_page("https://a.example", ["q2"], text="x" * 5000)
    big = web_page("https://b.example", ["q1"])
    chunks = [*chunks_of(small, ["a", "b"]), *chunks_of(big, ["c"])]
    result = await prefilter(
        queries(3),
        [small, big],
        chunks,
        method="bm25",
        pairing="found",
        embedder=None,
        top_k=50,
        passthrough_chars=8000,
    )
    q2 = [c for c in result.candidates if c.query_id == "q2"]
    assert len(q2) == 2
    assert all(c.passthrough for c in q2)
    assert not any(c.passthrough for c in result.candidates if c.query_id == "q1")


def many(count: int) -> tuple[list[Page], list[Chunk]]:
    page = web_page("https://a.example", ["q0"])
    return [page], chunks_of(page, [f"query word{n} text {n}" for n in range(count)])


def scored(page: Page, chunk: Chunk) -> str:
    return scoring_text(page.source.title, chunk.heading_path, chunk.text)


@pytest.mark.parametrize(("method", "expected"), [("bm25", 50), ("none", 300)])
async def test_top_k_per_query(method: str, expected: int) -> None:
    pages, chunks = many(300)
    result = await prefilter(
        queries(1), pages, chunks, method=method, pairing="found", embedder=None, top_k=50, passthrough_chars=8000
    )
    assert len(result.candidates) == expected
    assert result.method == method


async def test_embeddings_use_cache() -> None:
    pages, chunks = many(3)
    embedder = FakeEmbedder()
    first, last = scored(pages[0], chunks[0]), scored(pages[0], chunks[2])
    vector = (await embedder.embed([first]))[0]
    cache = {text_key(first): vector}
    embedder.calls.clear()
    result = await prefilter(
        queries(1),
        pages,
        chunks,
        method="embeddings",
        pairing="found",
        embedder=embedder,
        top_k=2,
        passthrough_chars=8000,
        cache=cache,
    )
    assert result.method == "embeddings"
    assert len(result.candidates) == 2
    assert len(embedder.calls) == 1
    assert first not in embedder.calls[0]
    assert text_key(last) in cache


class NearEmbedder:
    """The query and the `near` texts point one way, every other chunk the opposite way."""

    def __init__(self, chunk_texts: set[str], near: set[str]) -> None:
        self.chunk_texts = chunk_texts
        self.near = near

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if text in self.near or text not in self.chunk_texts else [-1.0, 0.1] for text in texts]

    async def describe(self) -> EmbedderInfo:
        return EmbedderInfo(model="near", dimension=2)


async def test_embeddings_keep_nearest() -> None:
    pages, chunks = many(6)
    near = {scored(pages[0], chunks[1]), scored(pages[0], chunks[4])}
    embedder = NearEmbedder({scored(pages[0], chunk) for chunk in chunks}, near)
    result = await prefilter(
        queries(1),
        pages,
        chunks,
        method="embeddings",
        pairing="found",
        embedder=embedder,
        top_k=2,
        passthrough_chars=8000,
    )
    assert result.method == "embeddings"
    assert {candidate.chunk_id for candidate in result.candidates} == {chunks[1].chunk_id, chunks[4].chunk_id}


class DownEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("connection refused")

    async def describe(self) -> EmbedderInfo:
        return EmbedderInfo(model="down", dimension=8)


async def test_embedder_down_falls_back_to_bm25() -> None:
    pages, chunks = many(60)
    result = await prefilter(
        queries(1),
        pages,
        chunks,
        method="embeddings",
        pairing="found",
        embedder=DownEmbedder(),
        top_k=50,
        passthrough_chars=8000,
    )
    assert result.method == "bm25"
    assert len(result.warnings) == 1
    assert "connection refused" in result.warnings[0]
    assert len(result.candidates) == 50


class ShrinkingEmbedder:
    """4-dimensional vectors on the first call, 3-dimensional afterwards (a fallback URL serving another model)."""

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        size = 4 if self.calls == 1 else 3
        return [[float(len(text) % 7 + 1)] * size for text in texts]

    async def describe(self) -> EmbedderInfo:
        return EmbedderInfo(model="m", dimension=4)


async def test_dimension_change_falls_back() -> None:
    pages, chunks = many(3)
    embedder = ShrinkingEmbedder()
    first = scored(pages[0], chunks[0])
    cache = {text_key(first): (await embedder.embed([first]))[0]}
    result = await prefilter(
        queries(1),
        pages,
        chunks,
        method="embeddings",
        pairing="found",
        embedder=embedder,
        top_k=2,
        passthrough_chars=8000,
        cache=cache,
    )
    assert result.method == "bm25"
    assert len(result.warnings) == 1


async def test_cache_put_error_falls_back(tmp_path: Path) -> None:
    pages, chunks = many(3)
    embedder = ShrinkingEmbedder()
    embedder.calls = 1
    cache = EmbeddingMapping(EmbeddingCache(tmp_path), "m", 4)
    result = await prefilter(
        queries(1),
        pages,
        chunks,
        method="embeddings",
        pairing="found",
        embedder=embedder,
        top_k=2,
        passthrough_chars=8000,
        cache=cache,
    )
    assert result.method == "bm25"
    assert len(result.warnings) == 1
    assert "3 dimensions" in result.warnings[0]
    assert "expected 4" in result.warnings[0]


async def test_embeds_scoring_text() -> None:
    pages, chunks = many(6)
    chunks = [chunk.model_copy(update={"heading_path": ["Results"]}) for chunk in chunks]
    embedder = FakeEmbedder()
    result = await prefilter(
        queries(1),
        pages,
        chunks,
        method="embeddings",
        pairing="found",
        embedder=embedder,
        top_k=2,
        passthrough_chars=8000,
    )
    assert f"{pages[0].source.title} > Results\n\n{chunks[0].text}" in embedder.calls[0]
    assert {candidate.chunk_id for candidate in result.candidates} <= {chunk.chunk_id for chunk in chunks}
    assert len(result.candidates) == 2


async def test_body_context_embeds_body_text() -> None:
    pages, chunks = many(6)
    chunks = [chunk.model_copy(update={"heading_path": ["Results"]}) for chunk in chunks]
    embedder = FakeEmbedder()
    await prefilter(
        queries(1),
        pages,
        chunks,
        method="embeddings",
        pairing="found",
        context="body",
        embedder=embedder,
        top_k=2,
        passthrough_chars=8000,
    )
    assert set(embedder.calls[0]) >= {chunk.text for chunk in chunks}
    assert not any(" > Results" in text for text in embedder.calls[0])

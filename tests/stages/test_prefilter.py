from pathlib import Path

import pytest

from wosarcher.adapters.fakes import FakeEmbedder
from wosarcher.models import Chunk, EmbedderInfo, Page
from wosarcher.runner.caches import EmbeddingMapping
from wosarcher.stages.prefilter import pairs, prefilter, text_key
from wosarcher.store.caches import EmbeddingCache

from .ranking_data import chunks_of, file_page, queries, web_page


def test_web_chunks_pair_with_finding_queries_only() -> None:
    page = web_page("https://a.example", ["q1", "q3"])
    chunks = chunks_of(page, ["one", "two"])
    paired = pairs(queries(4), [page], chunks)
    assert {query_id for query_id, found in paired.items() if found} == {"q1", "q3"}
    assert paired["q1"] == chunks


def test_file_chunk_pairs_with_every_query() -> None:
    page = file_page("notes.md")
    chunks = chunks_of(page, ["only"])
    paired = pairs(queries(3), [page], chunks)
    assert paired == {"q0": chunks, "q1": chunks, "q2": chunks}


async def test_small_input_is_passthrough() -> None:
    small = web_page("https://a.example", ["q2"], text="x" * 5000)
    big = web_page("https://b.example", ["q1"])
    chunks = [*chunks_of(small, ["a", "b"]), *chunks_of(big, ["c"])]
    result = await prefilter(
        queries(3), [small, big], chunks, method="bm25", embedder=None, top_k=50, passthrough_chars=8000
    )
    q2 = [c for c in result.candidates if c.query_id == "q2"]
    assert len(q2) == 2
    assert all(c.passthrough for c in q2)
    assert not any(c.passthrough for c in result.candidates if c.query_id == "q1")


def many(count: int) -> tuple[list[Page], list[Chunk]]:
    page = web_page("https://a.example", ["q0"])
    return [page], chunks_of(page, [f"query word{n} text {n}" for n in range(count)])


@pytest.mark.parametrize(("method", "expected"), [("bm25", 50), ("none", 300)])
async def test_top_k_per_query(method: str, expected: int) -> None:
    pages, chunks = many(300)
    result = await prefilter(queries(1), pages, chunks, method=method, embedder=None, top_k=50, passthrough_chars=8000)
    assert len(result.candidates) == expected
    assert result.method == method


async def test_embeddings_use_cache() -> None:
    pages, chunks = many(3)
    embedder = FakeEmbedder()
    vector = (await embedder.embed([chunks[0].text]))[0]
    cache = {text_key(chunks[0].text): vector}
    embedder.calls.clear()
    result = await prefilter(
        queries(1), pages, chunks, method="embeddings", embedder=embedder, top_k=2, passthrough_chars=8000, cache=cache
    )
    assert result.method == "embeddings"
    assert len(result.candidates) == 2
    assert len(embedder.calls) == 1
    assert chunks[0].text not in embedder.calls[0]
    assert text_key(chunks[2].text) in cache


class DownEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("connection refused")

    async def describe(self) -> EmbedderInfo:
        return EmbedderInfo(model="down", dimension=8)


async def test_embedder_down_falls_back_to_bm25() -> None:
    pages, chunks = many(60)
    result = await prefilter(
        queries(1), pages, chunks, method="embeddings", embedder=DownEmbedder(), top_k=50, passthrough_chars=8000
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
    cache = {text_key(chunks[0].text): (await embedder.embed([chunks[0].text]))[0]}
    result = await prefilter(
        queries(1), pages, chunks, method="embeddings", embedder=embedder, top_k=2, passthrough_chars=8000, cache=cache
    )
    assert result.method == "bm25"
    assert len(result.warnings) == 1


async def test_cache_put_error_falls_back(tmp_path: Path) -> None:
    pages, chunks = many(3)
    embedder = ShrinkingEmbedder()
    embedder.calls = 1
    cache = EmbeddingMapping(EmbeddingCache(tmp_path), "m", 4)
    result = await prefilter(
        queries(1), pages, chunks, method="embeddings", embedder=embedder, top_k=2, passthrough_chars=8000, cache=cache
    )
    assert result.method == "bm25"
    assert len(result.warnings) == 1
    assert "3 dimensions" in result.warnings[0]
    assert "expected 4" in result.warnings[0]

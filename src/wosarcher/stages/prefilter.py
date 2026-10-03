"""Prefilter: pair chunks with the queries they can answer, then keep the top pairs per query cheaply.

Web chunks pair with every query that found their page; file chunks pair with
every query. A query whose paired pages are short skips ranking (small-input
passthrough). Others keep `top_k` pairs by embedding similarity or BM25, or all
with `none`. An embedder failure or a vector of another dimension switches the
whole stage to BM25.
"""

import math
from collections.abc import MutableMapping, Sequence
from hashlib import sha256
from typing import Literal, cast, get_args

from wosarcher.lexical import bm25_scores, rank
from wosarcher.models import Candidate, Chunk, Page, PrefilterResult, Query
from wosarcher.ports import Embedder

Method = Literal["embeddings", "bm25", "none"]


def paired_pages(query: Query, pages: Sequence[Page]) -> list[Page]:
    """Web pages the query found, then every file, in page order."""
    web = [page for page in pages if page.source.kind == "web" and query.id in page.query_ids]
    files = [page for page in pages if page.source.kind == "file"]
    return [*web, *files]


def pairs(queries: Sequence[Query], pages: Sequence[Page], chunks: Sequence[Chunk]) -> dict[str, list[Chunk]]:
    """Each query ID's chunks, in page order then position."""
    by_source: dict[str, list[Chunk]] = {}
    for chunk in sorted(chunks, key=lambda chunk: chunk.position):
        by_source.setdefault(chunk.source_id, []).append(chunk)
    return {
        query.id: [chunk for page in paired_pages(query, pages) for chunk in by_source.get(page.source.source_id, [])]
        for query in queries
    }


def is_small(query: Query, pages: Sequence[Page], passthrough_chars: int) -> bool:
    distinct = {page.source.source_id: page for page in paired_pages(query, pages)}
    return sum(len(page.text) for page in distinct.values()) < passthrough_chars


def text_key(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


def top(values: Sequence[float], top_k: int) -> set[int]:
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))
    return set(order[:top_k])


def by_bm25(query: Query, chunks: Sequence[Chunk], top_k: int) -> list[Candidate]:
    texts = [chunk.text for chunk in chunks]
    values = bm25_scores(query.text, texts)
    kept = set(rank(query.text, texts, relative_threshold=0.0, max_results=top_k))
    return [
        Candidate(query_id=query.id, chunk_id=chunk.chunk_id, prefilter=values[i])
        for i, chunk in enumerate(chunks)
        if i in kept
    ]


async def embed_all(texts: Sequence[str], embedder: Embedder, cache: MutableMapping[str, list[float]]) -> None:
    """Embed, in one call, every distinct text not yet in `cache`."""
    missing = list(dict.fromkeys(text for text in texts if text_key(text) not in cache))
    if not missing:
        return
    vectors = await embedder.embed(missing)
    for text, vector in zip(missing, vectors, strict=True):
        cache[text_key(text)] = vector


def by_similarity(
    query: Query, chunks: Sequence[Chunk], top_k: int, cache: MutableMapping[str, list[float]]
) -> list[Candidate]:
    target = cache[text_key(query.text)]
    values = [cosine(target, cache[text_key(chunk.text)]) for chunk in chunks]
    kept = top(values, top_k)
    return [
        Candidate(query_id=query.id, chunk_id=chunk.chunk_id, prefilter=values[i])
        for i, chunk in enumerate(chunks)
        if i in kept
    ]


async def prefilter(
    queries: Sequence[Query],
    pages: Sequence[Page],
    chunks: Sequence[Chunk],
    *,
    method: str,
    embedder: Embedder | None,
    top_k: int,
    passthrough_chars: int,
    cache: MutableMapping[str, list[float]] | None = None,
) -> PrefilterResult:
    if method not in get_args(Method):
        raise ValueError(f"prefilter.provider '{method}' is not one of: {', '.join(get_args(Method))}")
    ran = cast(Method, method)
    paired = pairs(queries, pages, chunks)
    small = {query.id for query in queries if is_small(query, pages, passthrough_chars)}
    ranked = [query for query in queries if query.id not in small]
    warnings: list[str] = []
    vectors: MutableMapping[str, list[float]] = cache if cache is not None else {}

    similar: dict[str, list[Candidate]] = {}
    if ran == "embeddings":
        texts = [text for query in ranked for text in (query.text, *(chunk.text for chunk in paired[query.id]))]
        try:
            if embedder is None:
                raise RuntimeError("embedder not configured")
            await embed_all(texts, embedder, vectors)
            similar = {query.id: by_similarity(query, paired[query.id], top_k, vectors) for query in ranked}
        except Exception as error:
            warnings.append(f"embeddings prefilter failed, used bm25: {error}")
            ran = "bm25"

    candidates: list[Candidate] = []
    for query in queries:
        chunks_of = paired[query.id]
        if query.id in small:
            candidates.extend(Candidate(query_id=query.id, chunk_id=c.chunk_id, passthrough=True) for c in chunks_of)
        elif ran == "embeddings":
            candidates.extend(similar[query.id])
        elif ran == "bm25":
            candidates.extend(by_bm25(query, chunks_of, top_k))
        else:
            candidates.extend(Candidate(query_id=query.id, chunk_id=c.chunk_id) for c in chunks_of)
    return PrefilterResult(candidates=candidates, method=ran, warnings=warnings)

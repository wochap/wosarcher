"""Scorer: local BM25 over the given chunks, relative to the best chunk. No request."""

from wosarcher.lexical import bm25_scores
from wosarcher.models import Chunk, Query, Score

FALLBACK_COUNT = 25


class Bm25Scorer:
    name = "bm25"
    calibrated = False

    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
        raw = bm25_scores(query.text, [chunk.text for chunk in chunks])
        best = max(raw, default=0.0)
        if best > 0:
            values = [value / best for value in raw]
        else:
            values = [1.0 if position < FALLBACK_COUNT else 0.0 for position in range(len(chunks))]
        return [
            Score(query_id=query.id, chunk_id=chunk.chunk_id, value=value, scorer=self.name)
            for chunk, value in zip(chunks, values, strict=True)
        ]

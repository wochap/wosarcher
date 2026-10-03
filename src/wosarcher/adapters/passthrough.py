"""Scorer: every chunk gets 1.0, so the caller's order is kept. The last fallback."""

from wosarcher.models import Chunk, Query, Score


class PassthroughScorer:
    name = "passthrough"
    calibrated = False

    async def score(self, query: Query, chunks: list[Chunk]) -> list[Score]:
        return [Score(query_id=query.id, chunk_id=chunk.chunk_id, value=1.0, scorer=self.name) for chunk in chunks]

from collections.abc import Sequence

import pytest

from tests.adapters.conftest import chunks
from wosarcher.adapters import bm25
from wosarcher.adapters.bm25 import Bm25Scorer
from wosarcher.adapters.passthrough import PassthroughScorer
from wosarcher.models import Query

Q = Query(id="q1", text="lithium battery recycling")


async def test_relative_values(monkeypatch: pytest.MonkeyPatch) -> None:
    def raw(query: str, texts: Sequence[str]) -> list[float]:
        return [8.0, 4.0, 0.0]

    monkeypatch.setattr(bm25, "bm25_scores", raw)
    scores = await Bm25Scorer().score(Q, chunks("a", "b", "c"))
    assert [score.value for score in scores] == [1.0, 0.5, 0.0]
    assert {(score.query_id, score.scorer) for score in scores} == {("q1", "bm25")}


async def test_no_keyword_overlap() -> None:
    scores = await Bm25Scorer().score(Q, chunks(*(f"unrelated weather report {i}" for i in range(30))))
    assert [score.value for score in scores] == [1.0] * 25 + [0.0] * 5


async def test_bm25_not_calibrated() -> None:
    assert (Bm25Scorer.name, Bm25Scorer.calibrated) == ("bm25", False)


async def test_order_kept() -> None:
    items = chunks("c", "a", "b")
    scores = await PassthroughScorer().score(Q, items)
    assert [(score.chunk_id, score.value) for score in scores] == [(chunk.chunk_id, 1.0) for chunk in items]
    assert PassthroughScorer.calibrated is False

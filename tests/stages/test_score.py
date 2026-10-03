import pytest

from wosarcher.adapters.fakes import FakeScorer
from wosarcher.config import ScoreConfig
from wosarcher.models import Candidate, Chunk, Page, Query, QueryScores
from wosarcher.stages.score import _display, _keep_calibrated, _keep_relative, score

from .ranking_data import chunks_of, file_page, queries, web_page


def test_calibrated_threshold() -> None:
    assert _keep_calibrated([2.5, 1.5, 1.0], 1.5) == {0, 1}


def test_relative_threshold() -> None:
    assert _keep_relative([0.9, 0.5, 0.4], 0.5) == {0, 1}


def test_all_negative_keeps_best() -> None:
    assert _keep_relative([-3.0, -1.0, -2.0], 0.5) == {1}


def test_display() -> None:
    assert _display("jev", 2.4, 2.4) == pytest.approx(0.8)
    assert _display("bm25", 6.0, 6.0) == pytest.approx(1.0)
    assert _display("bm25", 3.0, 6.0) == pytest.approx(0.5)
    assert _display("rerank", 1.7, 1.7) == pytest.approx(1.0)
    assert _display("passthrough", 3.0, 3.0) is None


def setup(texts: list[str], query_ids: list[str]) -> tuple[list[Page], list[Chunk]]:
    page = web_page("https://a.example", query_ids)
    return [page], chunks_of(page, texts)


def every(qs: list[Query], chunks: list[Chunk], passthrough: bool = False) -> list[Candidate]:
    return [Candidate(query_id=q.id, chunk_id=c.chunk_id, passthrough=passthrough) for q in qs for c in chunks]


async def test_jev_display_threshold() -> None:
    pages, chunks = setup(["a", "b", "c"], ["q0"])
    qs = [Query(id="q0", text="anything")]
    jev = FakeScorer("jev", calibrated=True, values={chunks[0].chunk_id: 2.4, chunks[1].chunk_id: 1.0})
    result = await score(every(qs, chunks), qs, pages, chunks, jev, cfg=ScoreConfig(provider="jev"))
    assert result.queries[0].threshold_display == pytest.approx(0.5)
    assert [s.chunk_id for s in result.queries[0].passages] == [chunks[0].chunk_id]
    assert result.queries[0].passages[0].display == pytest.approx(0.8)


async def test_bm25_no_match_keeps_opening_pairs() -> None:
    pages, chunks = setup([f"nothing {n}" for n in range(15)], ["q0"])
    qs = [Query(id="q0", text="zebra")]
    result = await score(every(qs, chunks), qs, pages, chunks, None, cfg=ScoreConfig(provider="bm25"))
    kept = [s.chunk_id for s in result.scores if s.kept]
    assert kept == [c.chunk_id for c in chunks[:10]]


async def test_chunk_keeps_best_pair() -> None:
    page = file_page("notes.md")
    chunks = chunks_of(page, ["shared"])
    qs = queries(3)
    candidates = [Candidate(query_id=q, chunk_id=chunks[0].chunk_id) for q in ("q0", "q2")]

    class PerQuery(FakeScorer):
        async def score(self, query: Query, chunks: list[Chunk]):
            self.default = {"q0": 0.6, "q2": 0.8}[query.id]
            return await super().score(query, chunks)

    result = await score(candidates, qs, [page], chunks, PerQuery("rerank"), cfg=ScoreConfig(provider="rerank"))
    assert [(s.query_id, s.kept) for s in result.scores] == [("q0", False), ("q2", True)]


async def test_top_k_cap() -> None:
    pages, chunks = setup([f"c{n}" for n in range(12)], ["q0"])
    qs = [Query(id="q0", text="x")]
    rerank = FakeScorer("rerank", default=0.9)
    result = await score(every(qs, chunks), qs, pages, chunks, rerank, cfg=ScoreConfig(provider="rerank"))
    assert result.queries[0].kept == 10
    assert sum(s.kept for s in result.scores) == 10


async def test_small_input_scored_by_passthrough() -> None:
    small = web_page("https://s.example", ["q1"], text="x" * 100)
    big = web_page("https://b.example", ["q0"])
    small_chunks, big_chunks = chunks_of(small, ["a", "b"]), chunks_of(big, ["c"])
    qs = queries(2)
    candidates = [*every(qs[1:], small_chunks, passthrough=True), *every(qs[:1], big_chunks)]
    rerank = FakeScorer("rerank")
    result = await score(
        candidates, qs, [small, big], [*small_chunks, *big_chunks], rerank, cfg=ScoreConfig(provider="rerank")
    )
    assert {r.query_id: r.scorer for r in result.queries} == {"q0": "rerank", "q1": "passthrough"}
    assert [q.id for q, _ in rerank.calls] == ["q0"]
    q1 = result.queries[1]
    assert (q1.kept, q1.threshold_display) == (2, None)
    assert all(s.display is None for s in q1.passages)


class FailsSecond(FakeScorer):
    async def score(self, query: Query, chunks: list[Chunk]):
        if query.id == "q1":
            raise RuntimeError("reranker unreachable")
        return await super().score(query, chunks)


async def test_fallback_to_bm25() -> None:
    pages, chunks = setup(["query one", "query two"], ["q0", "q1", "q2"])
    qs = queries(3)
    seen: list[QueryScores] = []
    result = await score(
        every(qs, chunks),
        qs,
        pages,
        chunks,
        FailsSecond("rerank"),
        cfg=ScoreConfig(provider="rerank"),
        on_item=seen.append,
    )
    assert result.scorer == "bm25"
    assert [(f.item, f.reason) for f in result.failed] == [("rerank", "reranker unreachable")]
    assert all(s.scorer == "bm25" for s in result.scores)
    assert [r.scorer for r in seen] == ["bm25"] * 3
    assert any(not s.kept for s in result.scores)


async def test_everything_fails_ends_with_passthrough() -> None:
    pages, chunks = setup([f"c{n}" for n in range(12)], ["q0"])
    qs = queries(1)
    cfg = ScoreConfig(provider="rerank", fallback=["passthrough"])
    result = await score(every(qs, chunks), qs, pages, chunks, None, cfg=cfg)
    assert result.scorer == "passthrough"
    assert [f.item for f in result.failed] == ["rerank"]
    assert all(s.kept for s in result.scores)
    assert len(result.scores) == 12

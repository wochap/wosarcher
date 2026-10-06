import math

import pytest

from wosarcher.adapters.fakes import FakeScorer
from wosarcher.config import ScoreConfig
from wosarcher.models import Candidate, Chunk, Page, Query, QueryScores, Score, ScoreResult
from wosarcher.stages import score as scoring
from wosarcher.stages.score import ScoreChainError, _display, _keep_calibrated, _keep_relative, keep_once, score

from .ranking_data import chunks_of, file_page, queries, web_page


def test_calibrated_threshold() -> None:
    assert _keep_calibrated([2.5, 1.5, 1.0], 1.5) == ({0, 1}, None)


async def jev_stage(values: list[float], min_score: float) -> ScoreResult:
    pages, chunks = setup([f"c{n}" for n in range(len(values))], ["q0"])
    qs = [Query(id="q0", text="x")]
    jev = FakeScorer("jev", calibrated=True, values={c.chunk_id: v for c, v in zip(chunks, values, strict=True)})
    return await score(every(qs, chunks), qs, pages, chunks, jev, cfg=ScoreConfig(provider="jev", min_score=min_score))


async def test_calibrated_floor() -> None:
    result = await jev_stage([1.4, 1.1, 0.3], 2.0)
    assert [(s.kept, s.floor, s.dropped) for s in result.scores] == [
        (True, True, None),
        (False, False, "threshold"),
        (False, False, "threshold"),
    ]


async def test_calibrated_no_floor() -> None:
    result = await jev_stage([2.5, 1.5, 1.0], 1.5)
    assert [(s.kept, s.floor) for s in result.scores] == [(True, False), (True, False), (False, False)]


async def test_floor_pair_loses_to_other_query() -> None:
    pages, chunks = setup(["shared"], ["q0", "q1"])
    qs = [Query(id="q0", text="q0"), Query(id="q1", text="q1")]

    class PerQuery(FakeScorer):
        async def score(self, query: Query, chunks: list[Chunk]):
            self.default = {"q0": 1.0, "q1": 2.5}[query.id]
            return await super().score(query, chunks)

    cfg = ScoreConfig(provider="jev", min_score=2.0)
    both = await score(every(qs, chunks), qs, pages, chunks, PerQuery("jev", calibrated=True), cfg=cfg)
    assert [(s.query_id, s.kept, s.floor, s.dropped) for s in both.scores] == [
        ("q0", False, True, "other_query"),
        ("q1", True, False, None),
    ]


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


async def test_no_fallback_fails_stage() -> None:
    pages, chunks = setup(["query one"], ["q0", "q1"])
    qs = queries(2)
    cfg = ScoreConfig(provider="rerank", fallback=[])
    with pytest.raises(ScoreChainError, match="rerank: reranker unreachable"):
        await score(every(qs, chunks), qs, pages, chunks, FailsSecond("rerank"), cfg=cfg)


async def test_default_chain_ends_with_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object) -> list[float]:
        raise RuntimeError("bm25 broken")

    monkeypatch.setattr(scoring, "bm25_scores", broken)
    pages, chunks = setup([f"c{n}" for n in range(12)], ["q0"])
    qs = queries(1)
    result = await score(every(qs, chunks), qs, pages, chunks, None, cfg=ScoreConfig(provider="rerank"))
    assert result.scorer == "passthrough"
    assert [f.item for f in result.failed] == ["rerank", "bm25"]
    assert all(s.kept for s in result.scores)


class ByQuery(FakeScorer):
    """Rerank values per query, one per chunk in page order."""

    def __init__(self, values: dict[str, list[float]]) -> None:
        super().__init__("rerank")
        self.by_query = values

    async def score(self, query: Query, chunks: list[Chunk]):
        self.values = dict(zip((c.chunk_id for c in chunks), self.by_query[query.id], strict=True))
        return await super().score(query, chunks)


async def rerank_stage(values: dict[str, list[float]], **fields: object) -> ScoreResult:
    size = len(next(iter(values.values())))
    pages, chunks = setup([f"c{n}" for n in range(size)], list(values))
    qs = [Query(id=query_id, text="x") for query_id in values]
    cfg = ScoreConfig.model_validate({"provider": "rerank", **fields})
    return await score(every(qs, chunks), qs, pages, chunks, ByQuery(values), cfg=cfg)


def kept_values(result: ScoreResult, query_id: str = "q0") -> list[float]:
    return [s.value for s in result.scores if s.kept and s.query_id == query_id]


async def test_negative_logits_keep_two() -> None:
    result = await rerank_stage({"q0": [-1.2, -1.5, -4.0]})
    assert kept_values(result) == [-1.2, -1.5]
    assert [s.display for s in result.queries[0].passages] == [
        pytest.approx(0.23, abs=0.01),
        pytest.approx(0.18, abs=0.01),
    ]


async def test_large_logits() -> None:
    assert kept_values(await rerank_stage({"q0": [6.0, 2.0, -3.0]})) == [6.0, 2.0]


async def test_probability_scale_unchanged() -> None:
    result = await rerank_stage({"q0": [0.9, 0.5, 0.4]})
    assert kept_values(result) == [0.9, 0.5]
    assert [s.display for s in result.queries[0].passages] == [0.9, 0.5]


async def test_forced_probability_negative_keeps_best() -> None:
    result = await rerank_stage({"q0": [-1.2, -1.5, -4.0]}, rerank_scale="probability")
    assert kept_values(result) == [-1.2]


async def test_scale_decided_per_stage() -> None:
    result = await rerank_stage({"q0": [0.9, 0.5], "q1": [2.5, 1.0]})
    q0 = [s for s in result.scores if s.query_id == "q0"]
    assert q0[0].display == pytest.approx(1 / (1 + math.exp(-0.9)))


async def test_logit_best_pair_across_queries() -> None:
    page = file_page("notes.md")
    chunks = chunks_of(page, ["shared"])
    qs = queries(2)
    result = await score(
        every(qs, chunks), qs, [page], chunks, ByQuery({"q0": [-1.0], "q1": [-0.1]}), cfg=ScoreConfig(provider="rerank")
    )
    assert [(s.query_id, s.kept) for s in result.scores] == [("q0", False), ("q1", True)]
    assert [s.display for s in result.scores] == [pytest.approx(0.27, abs=0.01), pytest.approx(0.48, abs=0.01)]


async def test_raw_values_kept() -> None:
    result = await rerank_stage({"q0": [6.0, 2.0, -3.0]})
    assert [s.value for s in result.scores] == [6.0, 2.0, -3.0]


def dropped(result: ScoreResult, query_id: str = "q0") -> list[str | None]:
    return [s.dropped for s in result.scores if s.query_id == query_id]


async def test_drop_reason_threshold() -> None:
    assert dropped(await rerank_stage({"q0": [0.9, 0.4]})) == [None, "threshold"]


async def test_drop_reason_query_cap() -> None:
    result = await rerank_stage({"q0": [0.9 - n / 100 for n in range(11)]})
    assert dropped(result) == [None] * 10 + ["query_cap"]


async def test_drop_reason_other_query() -> None:
    result = await rerank_stage({"q0": [0.6], "q1": [0.8]})
    assert (dropped(result, "q0"), dropped(result, "q1")) == (["other_query"], [None])


async def test_capped_in_best_query_kept_in_another() -> None:
    result = await rerank_stage({"q1": [0.95] * 10 + [0.9], "q2": [0.1] * 10 + [0.8]})
    last = [s for s in result.scores if s.chunk_id == result.scores[10].chunk_id]
    assert [(s.query_id, s.kept, s.dropped) for s in last] == [("q1", False, "query_cap"), ("q2", True, None)]


async def test_passthrough_is_not_capped() -> None:
    pages, chunks = setup([f"c{n}" for n in range(14)], ["q0"])
    qs = [Query(id="q0", text="x")]
    result = await score(every(qs, chunks), qs, pages, chunks, None, cfg=ScoreConfig(provider="passthrough", top_k=10))
    assert sum(s.kept for s in result.scores) == 14


async def test_many_small_chunks_are_capped() -> None:
    pages, chunks = setup([f"c{n}" for n in range(11)], ["q0"])
    qs = [Query(id="q0", text="x")]
    candidates = every(qs, chunks, passthrough=True)
    result = await score(candidates, qs, pages, chunks, None, cfg=ScoreConfig(provider="rerank", top_k=6))
    assert [(s.chunk_id, s.kept, s.dropped) for s in result.scores] == [
        (piece.chunk_id, n < 6, None if n < 6 else "query_cap") for n, piece in enumerate(chunks)
    ]


def test_chunk_kept_once_across_rounds() -> None:
    plan = [Query(id="q0", text="m"), Query(id="q1", text="a"), Query(id="q6", text="b", round=2)]
    first = Score(query_id="q1", chunk_id="file", value=0.4, scorer="bm25", display=0.4, kept=True)
    later = Score(query_id="q6", chunk_id="file", value=0.9, scorer="bm25", display=0.9, kept=True, round=2)
    assert keep_once([first, later], plan) == [
        first,
        later.model_copy(update={"kept": False, "dropped": "other_query"}),
    ]


async def test_scorer_sees_scoring_text() -> None:
    pages, chunks = setup(["Positive in 62% of cases."], ["q0"])
    chunks = [chunks[0].model_copy(update={"heading_path": ["Results"]})]
    qs = [Query(id="q0", text="drug X")]
    rerank = FakeScorer("rerank", default=0.9)
    result = await score(every(qs, chunks), qs, pages, chunks, rerank, cfg=ScoreConfig(provider="rerank"))
    sent = rerank.calls[0][1][0]
    assert sent.text == f"{pages[0].source.title} > Results\n\nPositive in 62% of cases."
    assert sent.chunk_id == chunks[0].chunk_id
    assert [s.chunk_id for s in result.queries[0].passages] == [chunks[0].chunk_id]
    assert chunks[0].text == "Positive in 62% of cases."


async def test_body_context_scorer_sees_body_text() -> None:
    pages, chunks = setup(["Positive in 62% of cases."], ["q0"])
    chunks = [chunks[0].model_copy(update={"heading_path": ["Results"]})]
    qs = [Query(id="q0", text="drug X")]
    rerank = FakeScorer("rerank", default=0.9)
    await score(every(qs, chunks), qs, pages, chunks, rerank, cfg=ScoreConfig(provider="rerank"), context="body")
    assert rerank.calls[0][1][0].text == "Positive in 62% of cases."

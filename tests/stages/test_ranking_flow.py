from wosarcher.adapters.fakes import FakeEmbedder, FakeScorer
from wosarcher.config import ScoreConfig
from wosarcher.models import Query
from wosarcher.stages.prefilter import prefilter
from wosarcher.stages.score import score
from wosarcher.stages.select import budget, select

from .ranking_data import chunks_of, file_page, web_page


async def test_ranking_flow() -> None:
    queries = [
        Query(id="q0", text="battery recycling"),
        Query(id="q1", text="recycling cost"),
        Query(id="q2", text="lithium recovery"),
    ]
    a = web_page("https://a.example", ["q0", "q1"], text="a" * 9000)
    b = web_page("https://b.example", ["q2"], text="b" * 9000, rank=2)
    notes = file_page("notes.md", text="n" * 9000)
    pages = [a, b, notes]
    chunks = [
        *chunks_of(a, [f"battery recycling plants part {n} " * 20 for n in range(6)]),
        *chunks_of(b, [f"lithium recovery rate part {n} " * 20 for n in range(6)]),
        *chunks_of(notes, [f"recycling cost notes part {n} " * 20 for n in range(4)]),
    ]

    prefiltered = await prefilter(
        queries, pages, chunks, method="embeddings", embedder=FakeEmbedder(), top_k=5, passthrough_chars=8000
    )
    scored = await score(
        prefiltered.candidates,
        queries,
        pages,
        chunks,
        FakeScorer("rerank", default=0.7),
        cfg=ScoreConfig(provider="rerank"),
    )
    tokens = budget(context_window=8192, max_context_tokens=16000, prompt_reserve_tokens=2000, words=1200)
    context = select(
        queries[0].text,
        scored.scores,
        pages,
        chunks,
        queries,
        budget_tokens=tokens,
        max_per_source=5,
        file_share=0.5,
        chars_per_token=3.5,
        margin=1.1,
    ).context

    assert prefiltered.method == "embeddings"
    assert scored.scorer == "rerank"
    kept = {(s.query_id, s.chunk_id) for s in scored.scores if s.kept}
    assert context.passages
    assert all((p.query_id, p.chunk_id) in kept for p in context.passages)
    assert [p.n for p in context.passages] == list(range(1, len(context.passages) + 1))
    assert len({p.chunk_id for p in context.passages}) == len(context.passages)
    assert context.used_tokens <= context.budget_tokens == tokens

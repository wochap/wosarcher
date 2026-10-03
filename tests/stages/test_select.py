import pytest

from wosarcher.models import Chunk, Page, Score
from wosarcher.stages.select import budget, estimate_tokens, select

from .ranking_data import chunks_of, file_page, queries, web_page

# 350 characters estimate to 110 tokens, plus 16 for the label.
TEXT = "y" * 350
COST = 126


def test_budget_small_window() -> None:
    assert budget(context_window=8192, max_context_tokens=16000, prompt_reserve_tokens=2000, words=1200) == 3792


def test_budget_window_too_small() -> None:
    with pytest.raises(ValueError, match=r"llm\.context_window"):
        budget(context_window=4000, max_context_tokens=16000, prompt_reserve_tokens=2000, words=1200)


def test_estimate() -> None:
    assert estimate_tokens("z" * 700, chars_per_token=3.5, margin=1.1) == 220


def kept(query_id: str, chunks: list[Chunk], value: float = 1.0, is_kept: bool = True) -> list[Score]:
    return [
        Score(query_id=query_id, chunk_id=c.chunk_id, value=value - n / 100, scorer="rerank", display=0.5, kept=is_kept)
        for n, c in enumerate(chunks)
    ]


def run(scores: list[Score], pages: list[Page], chunks: list[Chunk], budget_tokens: int, count: int = 3):
    return select(
        "main",
        scores,
        pages,
        chunks,
        queries(count),
        budget_tokens=budget_tokens,
        max_per_source=5,
        file_share=0.5,
        chars_per_token=3.5,
        margin=1.1,
    )


def test_per_source_cap() -> None:
    page = web_page("https://a.example", ["q1"])
    chunks = chunks_of(page, [TEXT] * 8)
    context = run(kept("q1", chunks), [page], chunks, budget_tokens=100_000)
    assert len(context.passages) == 5


def test_round_robin_balances_queries() -> None:
    pages = [web_page(f"https://{n}.example", ["q1" if n < 10 else "q2"]) for n in range(12)]
    per_page = [chunks_of(page, [TEXT]) for page in pages]
    chunks = [chunk for found in per_page for chunk in found]
    one, two = chunks[:10], chunks[10:]
    cost = estimate_tokens(chunks[0].text, chars_per_token=3.5, margin=1.1) + 16
    context = run([*kept("q1", one), *kept("q2", two)], pages, chunks, budget_tokens=4 * cost + 3)
    assert [p.query_id for p in context.passages].count("q1") == 2
    assert [p.query_id for p in context.passages].count("q2") == 2


def test_too_big_is_skipped() -> None:
    page = web_page("https://a.example", ["q1"])
    chunks = chunks_of(page, ["b" * 3500, TEXT])
    context = run(kept("q1", chunks), [page], chunks, budget_tokens=200)
    assert [p.chunk_id for p in context.passages] == [chunks[1].chunk_id]


def test_files_only_use_whole_budget() -> None:
    page = file_page("notes.md")
    chunks = chunks_of(page, [TEXT + str(n) for n in range(4)])
    context = run(kept("q0", chunks), [page], chunks, budget_tokens=4 * (COST + 1))
    assert len(context.passages) == 4


def test_unused_web_share_goes_to_files() -> None:
    # Budget 10000: web gets 5000 but its passages use about 1000; files fill beyond their 5000.
    web = web_page("https://a.example", ["q1"])
    files = file_page("notes.md")
    web_chunks = chunks_of(web, ["w" * 2800])
    file_chunks = chunks_of(files, ["f" * 3500] * 1 + ["g" * 3500, "h" * 3500, "i" * 3500, "j" * 3500, "k" * 3500])
    cfile = [*kept("q0", file_chunks[:3]), *kept("q1", file_chunks[3:])]
    context = select(
        "main",
        [*cfile, *kept("q1", web_chunks)],
        [web, files],
        [*web_chunks, *file_chunks],
        queries(2),
        budget_tokens=10000,
        max_per_source=10,
        file_share=0.5,
        chars_per_token=3.5,
        margin=1.1,
    )
    file_tokens = sum(
        estimate_tokens(p.text, chars_per_token=3.5, margin=1.1) + 16
        for p in context.passages
        if p.source_id == files.source.source_id
    )
    assert file_tokens > 5000
    assert context.used_tokens <= 10000


def test_numbers_sources_and_rejected_pairs() -> None:
    a = web_page("https://a.example", ["q0"])
    b = web_page("https://b.example", ["q0"])
    a_chunks, b_chunks = chunks_of(a, [TEXT, TEXT + "2"]), chunks_of(b, [TEXT + "3", TEXT + "4"])
    scores = [*kept("q0", [*a_chunks, b_chunks[0]]), *kept("q0", b_chunks[1:], is_kept=False)]
    context = run(scores, [a, b], [*a_chunks, *b_chunks], budget_tokens=100_000)
    assert [p.n for p in context.passages] == [1, 2, 3]
    assert [p.chunk_id for p in context.passages] == [c.chunk_id for c in [*a_chunks, b_chunks[0]]]
    assert [p.source_id for p in context.passages] == [a.source.source_id] * 2 + [b.source.source_id]
    assert [s.source_id for s in context.sources] == [a.source.source_id, b.source.source_id]
    assert context.used_tokens == sum(
        estimate_tokens(p.text, chars_per_token=3.5, margin=1.1) + 16 for p in context.passages
    )

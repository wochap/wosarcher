from wosarcher.adapters.fakes import FakeSearcher
from wosarcher.models import Hit, Query
from wosarcher.stages.search import merge_hits, search


def hit(url: str, query_id: str, rank: int = 1, title: str = "t") -> Hit:
    return Hit(url=url, title=title, snippet="", rank=rank, query_ids=[query_id])


class FailingSearcher(FakeSearcher):
    async def search(self, query: Query) -> list[Hit]:
        if query.id == "q2":
            raise RuntimeError("searxng timed out")
        return await super().search(query)


def test_merge_keeps_both_query_ids_lowest_rank_first_title() -> None:
    merged = merge_hits(
        [[hit("https://a.example/x", "q1", 3, "first")], [hit("https://a.example/x", "q2", 1, "second")]]
    )
    assert [(h.url, h.query_ids, h.rank, h.title) for h in merged] == [
        ("https://a.example/x", ["q1", "q2"], 1, "first")
    ]


def test_merge_tracking_parameters() -> None:
    merged = merge_hits([[hit("https://a.example/x?utm_source=s", "q1")], [hit("https://A.example/x/", "q2")]])
    assert [(h.url, h.query_ids) for h in merged] == [("https://a.example/x", ["q1", "q2"])]


async def test_two_queries_one_page() -> None:
    searcher = FakeSearcher({"one": ["https://a.example/x"], "two": ["https://a.example/x", "https://b.example"]})
    seen: list[Hit] = []
    result = await search([Query(id="q1", text="one"), Query(id="q2", text="two")], searcher, on_item=seen.append)
    assert {h.url: h.query_ids for h in result.hits} == {
        "https://a.example/x": ["q1", "q2"],
        "https://b.example": ["q2"],
    }
    assert result.failures == []
    assert len(seen) == 3


async def test_one_search_fails() -> None:
    searcher = FailingSearcher({"one": ["https://a.example/x"]})
    result = await search([Query(id="q1", text="one"), Query(id="q2", text="two")], searcher)
    assert [h.url for h in result.hits] == ["https://a.example/x"]
    assert [(f.item, f.reason) for f in result.failures] == [("q2", "searxng timed out")]


async def test_initial_hits_reused() -> None:
    searcher = FakeSearcher({"sub": ["https://b.example"]})
    initial = [hit("https://a.example/x", "q0")]
    result = await search([Query(id="q1", text="sub")], searcher, initial=initial)
    assert {h.url: h.query_ids for h in result.hits} == {
        "https://a.example/x": ["q0"],
        "https://b.example": ["q1"],
    }
    assert [q.id for q in searcher.calls] == ["q1"]

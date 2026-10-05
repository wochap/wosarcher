from wosarcher.adapters.fakes import FakeSearcher
from wosarcher.models import Hit, Query
from wosarcher.stages.search import merge_hits, search


def hit(url: str, query_id: str, rank: int = 1, title: str = "t") -> Hit:
    return Hit(url=url, title=title, snippet="", rank=rank, query_ids=[query_id])


class FailingSearcher(FakeSearcher):
    async def search(self, query: Query, page: int = 1) -> list[Hit]:
        if query.id == "q2":
            raise RuntimeError("searxng timed out")
        return await super().search(query, page)


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


async def test_long_query_text_is_cut_for_the_searcher() -> None:
    searcher = FakeSearcher()
    text = " ".join(["word"] * 300)
    await search([Query(id="q0", text=text)], searcher)
    sent = searcher.calls[0].text
    assert len(sent) <= 200
    assert text.startswith(sent)
    assert text[len(sent)] == " "


Q1 = [Query(id="q1", text="one")]


async def test_result_cap() -> None:
    searcher = FakeSearcher({"one": [f"https://a.example/{n}" for n in range(20)]})
    result = await search(Q1, searcher, max_results=5)
    assert [(h.url, h.rank) for h in result.hits] == [(f"https://a.example/{n}", n + 1) for n in range(5)]


async def test_allowed_suffix() -> None:
    urls = ["https://www.gob.pe/a", "https://cej.pj.gob.pe/b", "https://notgob.pe/c", "https://infobae.com/d"]
    seen: list[Hit] = []
    result = await search(Q1, FakeSearcher({"one": urls}), allow=["gob.pe"], filter_pages=1, on_item=seen.append)
    assert [(h.url, h.rank) for h in result.hits] == [("https://www.gob.pe/a", 1), ("https://cej.pj.gob.pe/b", 2)]
    assert result.filtered == 2
    assert len(seen) == 2


async def test_block_wins() -> None:
    searcher = FakeSearcher({"one": ["https://facilito.gob.pe/x", "https://www.gob.pe/y"]})
    result = await search(Q1, searcher, allow=["gob.pe"], block=["facilito.gob.pe"])
    assert [h.url for h in result.hits] == ["https://www.gob.pe/y"]


async def test_block_list_only() -> None:
    searcher = FakeSearcher({"one": ["https://m.facebook.com/p", "https://a.example/x"]})
    result = await search(Q1, searcher, block=["facebook.com"])
    assert [h.url for h in result.hits] == ["https://a.example/x"]


async def test_no_filter() -> None:
    result = await search(Q1, FakeSearcher({"one": ["https://a.example/x", "https://b.example/y"]}))
    assert len(result.hits) == 2
    assert result.filtered == 0


async def test_same_url_dropped_twice() -> None:
    searcher = FakeSearcher({"one": ["https://x.com/a"], "two": ["https://x.com/a/"]})
    result = await search([*Q1, Query(id="q2", text="two")], searcher, block=["x.com"], filter_pages=1)
    assert result.filtered == 1


async def test_second_page_fills_the_query() -> None:
    page1 = ["https://www.gob.pe/1", "https://a.com/1", "https://sbs.gob.pe/2"]
    page2 = [f"https://www.gob.pe/p{n}" for n in range(4)]
    searcher = FakeSearcher(pages={"one": [page1, page2, ["https://www.gob.pe/late"]]})
    result = await search(Q1, searcher, max_results=5, allow=["gob.pe"])
    assert len(result.hits) == 5
    assert [h.rank for h in result.hits] == [1, 2, 3, 4, 5]
    assert searcher.requests == [("one", 1), ("one", 2)]


async def test_page_limit() -> None:
    searcher = FakeSearcher(pages={"one": [["https://a.com/1"], ["https://b.com/2"], ["https://gob.pe/3"]]})
    result = await search(Q1, searcher, allow=["gob.pe"], filter_pages=2)
    assert result.hits == []
    assert searcher.requests == [("one", 1), ("one", 2)]


async def test_empty_page_stops() -> None:
    searcher = FakeSearcher(pages={"one": [["https://a.com/1"], [], ["https://gob.pe/3"]]})
    await search(Q1, searcher, allow=["gob.pe"])
    assert searcher.requests == [("one", 1), ("one", 2)]


async def test_no_filter_reads_one_page() -> None:
    searcher = FakeSearcher(
        pages={"one": [["https://a.com/1", "https://b.com/2", "https://c.com/3"], ["https://d.com"]]}
    )
    result = await search(Q1, searcher, max_results=10)
    assert len(result.hits) == 3
    assert searcher.requests == [("one", 1)]


async def test_later_page_fails() -> None:
    searcher = FakeSearcher(
        {"one": ["https://gob.pe/1", "https://www.gob.pe/2", "https://a.com"]}, failing={("one", 2)}
    )
    result = await search(Q1, searcher, allow=["gob.pe"])
    assert len(result.hits) == 2
    assert [f.item for f in result.failures] == ["q1"]

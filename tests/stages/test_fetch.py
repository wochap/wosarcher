import asyncio

from wosarcher.adapters.fakes import FakeFetcher
from wosarcher.models import Hit, Page, Skipped
from wosarcher.stages.fetch import fetch


def hit(url: str, rank: int = 1, query_ids: tuple[str, ...] = ("q1",)) -> Hit:
    return Hit(url=url, title=url, snippet="", rank=rank, query_ids=list(query_ids))


class SlowFetcher(FakeFetcher):
    def __init__(self, pages: dict[str, str]) -> None:
        super().__init__(pages)
        self.in_flight = 0
        self.peak = 0

    async def fetch(self, url: str) -> Page:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        await asyncio.sleep(0.001)
        self.in_flight -= 1
        return await super().fetch(url)


async def test_one_page_fails() -> None:
    urls = ["https://a.example", "https://b.example", "https://c.example"]
    fetcher = FakeFetcher({url: "text" for url in urls}, failing={urls[1]})
    seen: list[Page | Skipped] = []
    result = await fetch([hit(url) for url in urls], fetcher, concurrency=6, max_pages=40, on_item=seen.append)
    assert [page.source.uri for page in result.pages] == [urls[0], urls[2]]
    assert [(f.item, f.reason) for f in result.failures] == [(urls[1], f"fake: cannot fetch {urls[1]}")]
    assert len(seen) == 3


async def test_empty_page() -> None:
    fetcher = FakeFetcher({"https://a.example": "  \n"})
    result = await fetch([hit("https://a.example")], fetcher, concurrency=6, max_pages=40)
    assert result.pages == []
    assert [f.reason for f in result.failures] == ["empty content"]


async def test_concurrency_limit() -> None:
    urls = [f"https://{n}.example" for n in range(10)]
    fetcher = SlowFetcher({url: "text" for url in urls})
    result = await fetch([hit(url) for url in urls], fetcher, concurrency=2, max_pages=40)
    assert len(result.pages) == 10
    assert fetcher.peak == 2


async def test_duplicate_url_fetched_once_with_hit_metadata() -> None:
    fetcher = FakeFetcher({"https://a.example/x": "text"})
    hits = [hit("https://a.example/x?utm_source=s", 4, ("q1",)), hit("https://A.example/x/", 2, ("q2",))]
    result = await fetch(hits, fetcher, concurrency=6, max_pages=40)
    assert fetcher.calls == ["https://a.example/x"]
    assert [(page.rank, page.query_ids) for page in result.pages] == [(2, ["q1", "q2"])]


async def test_fair_order() -> None:
    a = [hit(f"https://a{n}.example", n, ("q1",)) for n in (1, 2, 3)]
    b = [hit(f"https://b{n}.example", n, ("q2",)) for n in (1, 2, 3)]
    fetcher = FakeFetcher({h.url: "text" for h in [*a, *b]})
    result = await fetch([*a, *b], fetcher, concurrency=1, max_pages=4)
    assert fetcher.calls == ["https://a1.example", "https://b1.example", "https://a2.example", "https://b2.example"]
    assert len(result.pages) == 4
    assert result.unfetched == 2


async def test_failure_replaced() -> None:
    hits = [hit(f"https://{name}.example", rank) for rank, name in enumerate("xyz", 1)]
    fetcher = FakeFetcher({h.url: "text" for h in hits}, failing={"https://x.example"})
    result = await fetch(hits, fetcher, concurrency=1, max_pages=2)
    assert [page.source.uri for page in result.pages] == ["https://y.example", "https://z.example"]
    assert [f.item for f in result.failures] == ["https://x.example"]
    assert result.unfetched == 0


async def test_under_the_cap() -> None:
    urls = [f"https://{n}.example" for n in range(10)]
    fetcher = FakeFetcher({url: "text" for url in urls})
    result = await fetch([hit(url) for url in urls], fetcher, concurrency=6, max_pages=40)
    assert len(result.pages) == 10
    assert result.unfetched == 0

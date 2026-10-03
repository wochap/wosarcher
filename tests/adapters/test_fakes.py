from tests.adapters.conftest import chunks
from wosarcher.adapters.fakes import FakeEmbedder, FakeFetcher, FakeLLM, FakeScorer, FakeSearcher
from wosarcher.models import Message, Query
from wosarcher.ports import LLM, Embedder, Fetcher, Managed, Scorer, Searcher

searcher: Searcher = FakeSearcher()
fetcher: Fetcher = FakeFetcher()
embedder: Embedder = FakeEmbedder()
scorer: Scorer = FakeScorer()
llm: LLM = FakeLLM()
managed: list[Managed] = [FakeSearcher(), FakeFetcher(), FakeEmbedder(), FakeScorer(), FakeLLM()]
Q = Query(id="q1", text="battery")


async def test_fake_searcher() -> None:
    fake = FakeSearcher({"battery": ["https://a.com", "https://b.com"]})
    hits = await fake.search(Q)
    assert [(hit.url, hit.rank) for hit in hits] == [("https://a.com", 1), ("https://b.com", 2)]
    assert fake.calls == [Q]


async def test_fake_fetcher() -> None:
    fake = FakeFetcher({"https://a.com": "# A"}, failing={"https://b.com"})
    assert (await fake.fetch("https://a.com")).text == "# A"
    try:
        await fake.fetch("https://b.com")
    except RuntimeError:
        pass
    else:
        raise AssertionError("failing URL fetched")
    assert fake.calls == ["https://a.com", "https://b.com"]


async def test_fake_embedder() -> None:
    fake = FakeEmbedder()
    first, again, other = await fake.embed(["a", "a", "b"])
    assert first == again != other
    assert len(first) == (await fake.describe()).dimension == 8


async def test_fake_scorer() -> None:
    items = chunks("a", "b")
    fake = FakeScorer("jev", calibrated=True, values={items[0].chunk_id: 2.5}, default=0.5)
    assert [score.value for score in await fake.score(Q, items)] == [2.5, 0.5]
    assert fake.calibrated


async def test_fake_llm() -> None:
    fake = FakeLLM(["first reply", "second"])
    messages = [Message(role="user", content="hi")]
    assert (await fake.complete(messages, max_tokens=8)).text == "first reply"
    assert [part async for part in fake.stream(messages, max_tokens=8)] == ["second"]
    await fake.release()
    assert (fake.releases, len(fake.calls), (await fake.probe()).status) == (1, 2, "ok")

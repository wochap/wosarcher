from wosarcher.adapters.fakes import FakeFetcher, FakeLLM, FakeSearcher
from wosarcher.models import Attachment, Query
from wosarcher.stages.chunk import chunk
from wosarcher.stages.fetch import fetch
from wosarcher.stages.load import load, outline
from wosarcher.stages.plan import plan
from wosarcher.stages.search import search

QUERY = "battery recycling"


async def test_collection_flow() -> None:
    searcher = FakeSearcher(
        {
            QUERY: ["https://a.example/x", "https://b.example"],
            "recycling cost": ["https://a.example/x?utm_source=s", "https://c.example"],
        }
    )
    fetcher = FakeFetcher(
        {
            "https://a.example/x": "# Overview\nLithium recovery rates.",
            "https://b.example": "# Costs\nPlant costs per tonne.",
            "https://c.example": "Market size estimates.",
        }
    )
    llm = FakeLLM(['{"topic": "battery recycling", "queries": ["recycling cost"]}'])

    loaded = load([Attachment(name="notes.md", data=b"# Notes\n## Findings\nHydrometallurgy wins.\n")])
    initial = await search([Query(id="q0", text=QUERY)], searcher)
    planned = await plan(
        QUERY, initial.hits, [outline(page) for page in loaded.pages], llm, sources="both", max_sub_queries=3
    )
    found = await search(planned.queries[1:], searcher, initial=initial.hits)
    fetched = await fetch(found.hits, fetcher, concurrency=2, max_pages=40)
    chunked = chunk([*loaded.pages, *fetched.pages], size=1000, overlap=100)

    assert [query.id for query in planned.queries] == ["q0", "q1"]
    assert "Hydrometallurgy" in llm.calls[0][1].content
    assert [query.id for query in searcher.calls] == ["q0", "q1"]
    assert len(fetcher.calls) == 3
    pages = [*loaded.pages, *fetched.pages]
    source_ids = {page.source.source_id for page in pages}
    assert chunked.chunks
    assert all(item.source_id in source_ids for item in chunked.chunks)
    plan_ids = {query.id for query in planned.queries}
    assert all(set(page.query_ids) <= plan_ids for page in fetched.pages)
    assert {page.source.uri: page.query_ids for page in fetched.pages}["https://a.example/x"] == ["q0", "q1"]

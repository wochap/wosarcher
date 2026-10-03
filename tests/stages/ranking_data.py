"""Builders for pages, chunks, and queries shared by the ranking stage tests."""

from wosarcher.models import Chunk, Page, Query, Source, chunk_id, file_source_id, web_source_id


def queries(count: int) -> list[Query]:
    return [Query(id=f"q{n}", text=f"query {n}") for n in range(count)]


def web_page(url: str, query_ids: list[str], text: str = "x" * 9000, rank: int = 1) -> Page:
    source = Source(source_id=web_source_id(url), kind="web", uri=url, title=url)
    return Page(source=source, text=text, rank=rank, query_ids=query_ids)


def file_page(name: str, text: str = "x" * 9000) -> Page:
    source = Source(source_id=file_source_id(name.encode()), kind="file", uri=name, title=name)
    return Page(source=source, text=text)


def chunks_of(page: Page, texts: list[str]) -> list[Chunk]:
    source_id = page.source.source_id
    return [
        Chunk(chunk_id=chunk_id(source_id, n, text), source_id=source_id, position=n, text=text)
        for n, text in enumerate(texts)
    ]

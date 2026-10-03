import pytest
from pydantic import ValidationError

from wosarcher.models import (
    Chunk,
    Completion,
    Context,
    Contract,
    DoctorReport,
    EmbedderInfo,
    Hit,
    Message,
    Page,
    Passage,
    ProviderHealth,
    Query,
    Report,
    RunRequest,
    Score,
    Source,
    WritingOptions,
    chunk_id,
    file_source_id,
    normalise_url,
    web_source_id,
)

SOURCE = Source(source_id=web_source_id("https://example.com/a"), kind="web", uri="https://example.com/a", title="A")
CHUNK = Chunk(
    chunk_id=chunk_id(SOURCE.source_id, 0, "text"),
    source_id=SOURCE.source_id,
    position=0,
    text="text",
    heading_path=("Title", "Part"),
)
PASSAGE = Passage(n=1, chunk_id=CHUNK.chunk_id, source_id=SOURCE.source_id, query_id="q1", text="text", score=0.9)
HEALTH = ProviderHealth(
    block="score",
    provider="rerank",
    base_url="http://desktop.lan:8001/v1",
    device="desktop:gpu0",
    status="ok",
    model="reranker",
    latency_ms=12.5,
    unload="no",
)
SAMPLES: list[Contract] = [
    RunRequest(query="what", attachments=("notes.md",), until="select", writing=WritingOptions(words=500)),
    Query(query_id="q1", text="what"),
    Hit(url="https://example.com/a", title="A", snippet="s", rank=2, query_ids=("q1", "q2")),
    SOURCE,
    Page(source=SOURCE, markdown="# A"),
    CHUNK,
    Score(query_id="q1", chunk_id=CHUNK.chunk_id, value=2.5, scorer="jev"),
    PASSAGE,
    Context(passages=(PASSAGE,), sources=(SOURCE,), scorer="jev"),
    Report(markdown="text [1]", sources=(SOURCE,)),
    WritingOptions(),
    Message(role="user", content="hi"),
    Completion(text="hello", input_tokens=3, output_tokens=1),
    EmbedderInfo(model="Qwen3-Embedding-0.6B", dimension=1024),
    HEALTH,
    DoctorReport(providers=(HEALTH,), warnings=("score cannot unload",)),
]


@pytest.mark.parametrize("value", SAMPLES, ids=lambda value: type(value).__name__)
def test_round_trip(value: Contract) -> None:
    assert type(value).model_validate_json(value.model_dump_json()) == value


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="surprise"):
        Query.model_validate_json('{"query_id": "q1", "text": "x", "surprise": 1}')


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Example.COM/a", "https://example.com/a"),
        ("https://example.com/a#top", "https://example.com/a"),
        ("https://example.com/a/", "https://example.com/a"),
        ("https://example.com/a?utm_source=x&fbclid=1&gclid=2&utm_medium=y", "https://example.com/a"),
        ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
        ("https://example.com/a?id=42&utm_campaign=z", "https://example.com/a?id=42"),
    ],
)
def test_normalise_url(url: str, expected: str) -> None:
    assert normalise_url(url) == expected


def test_normalised_urls_share_source_id() -> None:
    assert web_source_id("https://Example.com/a/?utm_source=x#top") == web_source_id("https://example.com/a")


def test_same_file_content_shares_source_id() -> None:
    assert file_source_id(b"same text") == file_source_id(b"same text")
    assert file_source_id(b"same text") != file_source_id(b"other text")


def test_chunk_ids_are_deterministic() -> None:
    texts = ["first part", "second part"]
    first = [chunk_id(SOURCE.source_id, n, text) for n, text in enumerate(texts)]
    second = [chunk_id(SOURCE.source_id, n, text) for n, text in enumerate(texts)]
    assert first == second
    assert len(set(first)) == 2


def test_writing_option_defaults() -> None:
    options = WritingOptions()
    assert (options.tone, options.tone_instructions, options.words) == ("objective", "", 1200)
    assert (options.language, options.citation_marker, options.reference_style) == ("english", "numeric", "APA")


def test_words_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="words"):
        WritingOptions(words=0)


def test_unknown_citation_marker() -> None:
    with pytest.raises(ValidationError, match="citation_marker") as error:
        WritingOptions.model_validate({"citation_marker": "footnote"})
    assert "'numeric', 'superscript' or 'author-year'" in str(error.value)


def test_one_chunk_two_queries_gives_two_scores() -> None:
    scores = [Score(query_id=q, chunk_id=CHUNK.chunk_id, value=1.0, scorer="rerank") for q in ("q1", "q2")]
    assert {score.query_id for score in scores} == {"q1", "q2"}
    assert all(score.scorer == "rerank" for score in scores)

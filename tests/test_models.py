import pytest
from pydantic import ValidationError

from wosarcher.models import (
    Attachment,
    Candidate,
    Chunk,
    ChunkResult,
    Completion,
    Context,
    Contract,
    DoctorReport,
    EmbedderInfo,
    FetchResult,
    Hit,
    LoadResult,
    Message,
    Page,
    Passage,
    Plan,
    PrefilterResult,
    ProviderHealth,
    Query,
    QueryScores,
    Reference,
    Report,
    RunRequest,
    Score,
    ScoreResult,
    SearchResult,
    Skipped,
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
    heading_path=["Title", "Part"],
    page_id="4",
    block_ids=["p4-b1"],
)
SCORE = Score(query_id="q1", chunk_id=CHUNK.chunk_id, value=2.4, scorer="jev", display=0.8, kept=True)
PASSAGE = Passage(
    n=1,
    chunk_id=CHUNK.chunk_id,
    source_id=SOURCE.source_id,
    query_id="q1",
    text="text",
    heading_path=["Title"],
    page_id="4",
    block_ids=["p4-b1"],
    scorer="jev",
    display=0.8,
)
QUERY_SCORES = QueryScores(query_id="q1", scorer="jev", scored=3, kept=1, threshold_display=0.5, passages=[SCORE])
HIT = Hit(url="https://example.com/a", title="A", snippet="s", rank=2, query_ids=["q1", "q2"])
PAGE = Page(source=SOURCE, text="# A", truncated=True, rank=2, query_ids=["q1"])
SKIPPED = Skipped(item="q2", reason="timeout")
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
    Query(id="q1", text="what"),
    Plan(queries=[Query(id="q0", text="what")], warnings=["planner answer had no query list"]),
    HIT,
    SOURCE,
    PAGE,
    CHUNK,
    Attachment(name="notes/a.md", data=b"# A\n"),
    SKIPPED,
    SearchResult(hits=[HIT], failures=[SKIPPED]),
    FetchResult(pages=[PAGE], failures=[SKIPPED]),
    LoadResult(pages=[PAGE], skipped=[SKIPPED]),
    ChunkResult(chunks=[CHUNK], duplicates=1),
    SCORE,
    Candidate(query_id="q1", chunk_id=CHUNK.chunk_id, prefilter=0.7),
    Candidate(query_id="q2", chunk_id=CHUNK.chunk_id, passthrough=True),
    PrefilterResult(candidates=[], method="bm25", warnings=["embedder down"]),
    QUERY_SCORES,
    ScoreResult(scores=[SCORE], scorer="bm25", failed=[Skipped(item="rerank", reason="down")], queries=[QUERY_SCORES]),
    PASSAGE,
    Context(query="what", passages=[PASSAGE], sources=[SOURCE], budget_tokens=3792, used_tokens=20),
    Report(
        body="text [1]",
        markdown="text [1]\n\n## References",
        cited=[1],
        references=[Reference(source_id=SOURCE.source_id, entry="*A*", passages=[1])],
        warnings=["unknown citation [7]"],
    ),
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
        Query.model_validate_json('{"id": "q1", "text": "x", "surprise": 1}')


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

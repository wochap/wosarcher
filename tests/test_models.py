from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from wosarcher.models import (
    Answer,
    Attachment,
    Candidate,
    CatalogRecord,
    Chunk,
    ChunkResult,
    Completion,
    Context,
    Contract,
    DoctorReport,
    DroppedRecord,
    EmbedderInfo,
    ExtractedRecord,
    FetchResult,
    Hit,
    InputAnsweredData,
    LoadResult,
    Message,
    Node,
    Page,
    Passage,
    Pause,
    Plan,
    PrefilterResult,
    ProviderHealth,
    Query,
    QueryScores,
    Question,
    QuestionOption,
    Reference,
    Report,
    RunRecord,
    RunRequest,
    Score,
    ScoreResult,
    SearchResult,
    Seed,
    SelectSkip,
    Skipped,
    Source,
    Structure,
    StructureField,
    WaveEntry,
    WritingOptions,
    answer_text,
    check_answers,
    chunk_id,
    file_source_id,
    is_node_query_id,
    node_children_query_id,
    node_self_query_id,
    normalise_url,
    parse_node_query_id,
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
    RunRequest(query="what", attachments=["notes.md"], until="select"),
    Query(id="q1", text="what"),
    Plan(queries=[Query(id="q0", text="what")], warnings=["planner answer had no query list"]),
    HIT,
    SOURCE,
    PAGE,
    Page(source=SOURCE, text="## a\n1", format="json"),
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
    Score(query_id="q1", chunk_id=CHUNK.chunk_id, value=0.4, scorer="rerank", display=0.4, dropped="query_cap"),
    SelectSkip(chunk_id=CHUNK.chunk_id, query_id="q1", reason="source_cap"),
    SelectSkip(chunk_id=CHUNK.chunk_id, query_id="q2", reason="budget", tokens_needed=420, tokens_left=96),
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
    assert options.format == "report"


def test_unknown_format() -> None:
    with pytest.raises(ValidationError, match="format") as error:
        WritingOptions.model_validate({"format": "summary"})
    assert "'report' or 'answer'" in str(error.value)


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


def test_unknown_drop_reason() -> None:
    with pytest.raises(ValidationError, match="dropped"):
        Score.model_validate({"query_id": "q1", "chunk_id": "c", "value": 1.0, "scorer": "jev", "dropped": "budget"})


def test_report_without_continuation_fields() -> None:
    report = Report.model_validate_json('{"body": "x", "markdown": "x", "cited": [], "references": []}')
    assert (report.continuations, report.truncated) == (0, False)


# Catalog contracts


TYPES = ["power", "ministry", "public_body", "regional_government", "office", "court", "body"]


FIELDS: list[dict[str, Any]] = [
    {"name": "id", "type": "slug"},
    {"name": "name", "type": "text", "required": True},
    {"name": "type", "type": "enum", "values": TYPES},
    {"name": "parent_id", "type": "ref"},
    {"name": "head_name", "type": "text", "volatile": True, "dated_by": "verified_on"},
    {"name": "verified_on", "type": "date"},
    {"name": "website", "type": "url"},
]


def structure_data(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "fields": FIELDS,
        "relation": "organismos públicos adscritos o dependientes",
        "seeds": [{"name": f"Seed {i}", "type": "power", "url": f"https://s{i}.gob.pe"} for i in range(6)],
        "leaf_types": ["regional_government", "office"],
        "expand": "both",
        "limits": {"max_depth": 3, "max_nodes": 200, "pages_per_node": 2},
    }
    data.update(changes)
    return data


def with_fields(*extra: dict[str, Any], drop: str | None = None) -> dict[str, object]:
    fields = [f for f in FIELDS if f["name"] != drop]
    return structure_data(fields=[*fields, *extra])


def test_valid_structure() -> None:
    structure = Structure.model_validate(structure_data())
    assert structure.name_field.name == "name"
    assert structure.slug_field is not None
    assert structure.slug_field.name == "id"
    assert structure.ref_field is not None
    assert structure.ref_field.name == "parent_id"
    assert structure.enum_field.name == "type"
    assert structure.types == TYPES
    assert structure.is_expandable("power", 0)
    assert not structure.is_expandable("office", 1)
    assert not structure.is_expandable("power", 3)
    assert Structure.model_validate_json(structure.model_dump_json()) == structure


def test_structure_defaults() -> None:
    data = structure_data()
    for key in ("leaf_types", "expand", "limits"):
        del data[key]
    structure = Structure.model_validate(data)
    assert (structure.expand, structure.limits.max_depth, structure.limits.max_nodes) == ("both", 3, 200)


def test_two_enum_fields() -> None:
    with pytest.raises(ValidationError, match="type, kind"):
        Structure.model_validate(with_fields({"name": "kind", "type": "enum", "values": ["a"]}))


def test_no_enum_field() -> None:
    with pytest.raises(ValidationError, match="exactly one enum"):
        Structure.model_validate(with_fields(drop="type"))


def test_two_slug_fields() -> None:
    with pytest.raises(ValidationError, match=r"slug field .*id, code"):
        Structure.model_validate(with_fields({"name": "code", "type": "slug"}))


def test_two_ref_fields() -> None:
    with pytest.raises(ValidationError, match=r"ref field .*parent_id, other"):
        Structure.model_validate(with_fields({"name": "other", "type": "ref"}))


def test_no_required_text_field() -> None:
    with pytest.raises(ValidationError, match="required text field"):
        Structure.model_validate(with_fields(drop="name"))


def test_name_field_is_first_required_text() -> None:
    data = structure_data()
    data["fields"] = [{"name": "acronym", "type": "text", "required": True}, *data["fields"]]  # type: ignore[misc]
    assert Structure.model_validate(data).name_field.name == "acronym"


def test_seed_type_outside_enum() -> None:
    with pytest.raises(ValidationError, match=r"Seed X.*agency"):
        Structure.model_validate(structure_data(seeds=[{"name": "Seed X", "type": "agency"}]))


def test_leaf_type_outside_enum() -> None:
    with pytest.raises(ValidationError, match="leaf type 'shop'"):
        Structure.model_validate(structure_data(leaf_types=["shop"]))


@pytest.mark.parametrize("dated_by", [None, "website", "missing"])
def test_volatile_without_date_field(dated_by: str | None) -> None:
    field: dict[str, Any] = {"name": "budget", "type": "text", "volatile": True, "dated_by": dated_by}
    with pytest.raises(ValidationError, match="budget"):
        Structure.model_validate(with_fields(field))


def test_volatile_only_on_text() -> None:
    with pytest.raises(ValidationError, match="website: only text"):
        Structure.model_validate(
            with_fields({"name": "website", "type": "url", "volatile": True, "dated_by": "verified_on"}, drop="website")
        )


def test_bad_field_name() -> None:
    with pytest.raises(ValidationError, match=r"Head Name.*\^\[a-z\]"):
        Structure.model_validate(with_fields({"name": "Head Name", "type": "text"}))


def test_duplicate_field_name() -> None:
    with pytest.raises(ValidationError, match="unique: website"):
        Structure.model_validate(with_fields({"name": "website", "type": "url"}))


@pytest.mark.parametrize("values", [[], ["a", "a"], [""], [str(i) for i in range(41)]])
def test_bad_enum_values(values: list[str]) -> None:
    fields = [f for f in FIELDS if f["name"] != "type"]
    with pytest.raises(ValidationError, match="enum"):
        Structure.model_validate(structure_data(fields=[*fields, {"name": "type", "type": "enum", "values": values}]))


@pytest.mark.parametrize(
    "changes",
    [
        {"relation": ""},
        {"relation": "x" * 201},
        {"seeds": []},
        {"seeds": [{"name": "S", "type": "power", "url": "ftp://x"}]},
        {"limits": {"max_depth": 11}},
        {"limits": {"max_nodes": 5001}},
        {"limits": {"pages_per_node": 0}},
        {"expand": "crawl"},
    ],
)
def test_structure_value_ranges(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Structure.model_validate(structure_data(**changes))


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (Structure, structure_data(colour="red")),
        (Seed, {"name": "S", "type": "power", "colour": "red"}),
        (Node, {"id": "a", "name": "A", "type": "power", "colour": "red"}),
        (ExtractedRecord, {"node_id": "a", "record": {}, "colour": "red"}),
        (CatalogRecord, {"records": [], "nodes": 0, "reason": "frontier empty", "colour": "red"}),
        (WaveEntry, {"wave": 1, "colour": "red"}),
    ],
)
def test_catalog_unknown_field_rejected(model: type[Contract], data: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="colour"):
        model.model_validate(data)


def test_unknown_field_key_rejected() -> None:
    with pytest.raises(ValidationError, match="colour"):
        Structure.model_validate(with_fields({"name": "x", "type": "text", "colour": "red"}))


def test_catalog_contracts_round_trip() -> None:
    node = Node(
        id="mef",
        name="MEF",
        type="ministry",
        parent_id="poder-ejecutivo",
        depth=1,
        url="https://mef.gob.pe",
        wave=2,
        status="extracted",
        expanded=True,
        found_by="search",
        pages=["s1"],
        flags=["f"],
    )
    record = ExtractedRecord(
        node_id="mef", record={"name": "MEF", "website": None}, sources={"name": "https://mef.gob.pe"}
    )
    catalog = CatalogRecord(
        records=[{"id": "mef", "name": "MEF", "sources": {}, "flags": []}],
        dropped=[DroppedRecord(node_id="x", field="name")],
        nodes=2,
        waves=[WaveEntry(wave=1, expanded=1, found=1, records=1)],
        reason="frontier empty",
        note="No unexpanded nodes left after wave 1.",
        fill={"name": 1},
        by_type={"ministry": 1},
        by_depth={"1": 1},
    )
    for value in (node, record, catalog, Structure.model_validate(structure_data())):
        assert type(value).model_validate_json(value.model_dump_json()) == value


def test_node_query_ids() -> None:
    assert (node_self_query_id(4), node_children_query_id(4)) == ("n4s", "n4c")
    assert parse_node_query_id("n12c") == (12, "c")
    assert parse_node_query_id("q1") is None
    assert not is_node_query_id("n4x")
    query = Query(id="n4s", text="MEF ministry", round=2, node_id="mef")
    assert Query.model_validate_json(query.model_dump_json()) == query
    assert Query(id="q0", text="q").node_id is None


def test_run_request_kind_and_structure() -> None:
    assert RunRequest(query="q").kind == "research"
    request = RunRequest(query="brief", kind="catalog", structure=Structure.model_validate(structure_data()))
    assert RunRequest.model_validate_json(request.model_dump_json()) == request
    record = RunRecord.model_validate(
        {
            "run_id": "r",
            "created_at": "2026-01-01T00:00:00Z",
            "request": request.model_dump(),
            "profile": "p",
            "settings": {},
        }
    )
    assert record.kind == "catalog"
    assert record.structure == request.structure
    with pytest.raises(ValidationError):
        RunRequest(query="q", kind="crawl")  # type: ignore[arg-type]


def test_output_defaults_to_table() -> None:
    structure = Structure.model_validate(structure_data())
    assert structure.output == "table"
    assert not structure.wants_report


def test_invalid_output_names_the_values() -> None:
    with pytest.raises(ValidationError) as error:
        Structure.model_validate(structure_data(output="summary"))
    text = str(error.value)
    assert "output" in text
    assert all(value in text for value in ("table", "report", "both"))


def test_record_language_default_and_invalid() -> None:
    assert Structure.model_validate(structure_data()).record_language == ""
    with pytest.raises(ValidationError, match="record_language"):
        Structure.model_validate(structure_data(record_language="spanish"))


# Run questions


def options(*recommended: bool) -> list[QuestionOption]:
    return [QuestionOption(id="abcdef"[n], label=f"Option {n}", recommended=mark) for n, mark in enumerate(recommended)]


def test_question_without_recommendation_takes_the_first() -> None:
    question = Question(id="q1", text="t", kind="single", options=options(False, False))
    assert question.recommended_ids() == ["a"]


def test_question_with_several_recommendations_takes_the_first_marked() -> None:
    question = Question(id="q1", text="t", kind="confirm", options=options(False, True, True))
    assert question.recommended_ids() == ["b"]


def test_multi_keeps_any_number_of_recommendations() -> None:
    assert Question(id="q1", text="t", kind="multi", options=options(True, True, False)).recommended_ids() == ["a", "b"]
    assert Question(id="q1", text="t", kind="multi", options=options(False, False)).recommended_ids() == []


def test_confirm_cannot_allow_other() -> None:
    with pytest.raises(ValidationError, match="confirm"):
        Question(id="q1", text="t", kind="confirm", options=options(True, False), allow_other=True)


def test_pause_round_trip() -> None:
    question = Question(id="q1", text="t", kind="multi", options=options(True, False), allow_other=True)
    pause = Pause(
        id=1,
        kind="round",
        after=2,
        questions=[question],
        created=datetime(2026, 1, 1, tzinfo=UTC),
        timeout=60,
        max_wait=1800,
        answers=[Answer(question_id="q1", other="Add a query")],
        answered_by="user",
    )
    assert Pause.model_validate_json(pause.model_dump_json()) == pause


def test_pause_needs_one_to_four_questions() -> None:
    question = Question(id="q1", text="t", kind="single", options=options(True, False))
    created = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        Pause(id=1, kind="clarify", questions=[], created=created, timeout=0, max_wait=60)
    with pytest.raises(ValidationError):
        Pause(id=1, kind="clarify", questions=[question] * 5, created=created, timeout=0, max_wait=60)


def test_unknown_event_field_rejected() -> None:
    with pytest.raises(ValidationError, match="surprise"):
        InputAnsweredData.model_validate(
            {"pause_id": 1, "answers": [], "answered_by": "user", "seconds_waited": 1, "surprise": 1}
        )


def test_check_answers() -> None:
    question = Question(id="q1", text="t", kind="single", options=options(True, False))
    multi = Question(id="q2", text="t", kind="multi", options=options(True, False), allow_other=True)
    ok = [Answer(question_id="q1", option_ids=["a"]), Answer(question_id="q2", other="Diario Oficial")]
    check_answers([question, multi], ok)
    for bad, text in [
        ([ok[0]], "q2: no answer"),
        ([Answer(question_id="q1", option_ids=["z"]), ok[1]], "q1: unknown option z"),
        ([Answer(question_id="q1", option_ids=["a", "b"]), ok[1]], "q1: single takes one option"),
        ([Answer(question_id="q1", option_ids=["a"], other="x"), ok[1]], "q1: does not allow other"),
    ]:
        with pytest.raises(ValueError, match=text):
            check_answers([question, multi], bad)


def test_answer_text() -> None:
    question = Question(id="q1", text="t", kind="multi", options=options(True, False), allow_other=True)
    assert answer_text(question, Answer(question_id="q1", option_ids=["a", "b"], other=" more ")) == (
        "Option 0, Option 1, more"
    )


def test_field_help_round_trip_and_defaults() -> None:
    field = StructureField(name="website", type="url", description="Official site", example="https://x.test")
    assert StructureField.model_validate_json(field.model_dump_json()) == field
    bare = StructureField(name="website", type="url")
    assert (bare.description, bare.example) == ("", "")


@pytest.mark.parametrize("kind", ["slug", "ref"])
def test_example_rejected_on_generated_fields(kind: str) -> None:
    with pytest.raises(ValidationError, match=r"field id: a (slug|ref) field takes no example"):
        StructureField(name="id", type=kind, example="x")  # type: ignore[arg-type]
    assert StructureField(name="id", type=kind, description="the id").example == ""  # type: ignore[arg-type]


def test_field_help_limits() -> None:
    with pytest.raises(ValidationError):
        StructureField(name="a", type="text", description="x" * 201)
    with pytest.raises(ValidationError):
        StructureField(name="a", type="text", example="x" * 81)

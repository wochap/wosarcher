"""Run contracts: stage order, events, records, run settings, secrets, and usage totals."""

import json
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError
from typer.testing import CliRunner

from wosarcher.cli import app
from wosarcher.config import DEFAULT_STAGE_TIMEOUTS, Settings, redact, resolve, restore_secrets
from wosarcher.http import UsageLedger
from wosarcher.models import (
    EVENT_TYPES,
    STAGES,
    Context,
    GapReadyData,
    HitFoundData,
    KeptPassage,
    PageFailedData,
    PageFetchedData,
    PassagesScoredData,
    PlanReadyData,
    Query,
    ReportTextData,
    ResearchDoneData,
    ResourceData,
    RoundDoneData,
    RunCancelledData,
    RunDoneData,
    RunFailedData,
    RunOutput,
    RunQueuedData,
    RunRecord,
    RunRequest,
    RunStartedData,
    Stage,
    StageDoneData,
    StageFailedData,
    StageProgressData,
    StageStartedData,
    UsageTotals,
    make_event,
    parse_event,
)

TS = datetime(2026, 1, 1, tzinfo=UTC)
PASSAGE = KeptPassage(
    chunk_id="c", source_id="s", title="T", uri="https://x.test", heading_path=["A"], text="t", display=0.8
)
DATA: dict[str, BaseModel] = {
    "run.queued": RunQueuedData(position=2, limit=1),
    "run.started": RunStartedData(query="q", profile="p", parent_run_id=None, version=1, until="select"),
    "run.done": RunDoneData(until=None, totals=UsageTotals(input_tokens=3, cost=0.5)),
    "run.failed": RunFailedData(stage="plan", error="boom"),
    "run.cancelled": RunCancelledData(stage="fetch"),
    "stage.started": StageStartedData(device="desktop:gpu0", provider="rerank"),
    "stage.progress": StageProgressData(done=1, total=4, failed=0),
    "stage.done": StageDoneData(count=3, seconds=1.5, provider="bm25", warnings=["w"]),
    "stage.failed": StageFailedData(error="rerank: down", next="bm25"),
    "resource.waiting": ResourceData(device="desktop:gpu0", released_stage="score"),
    "resource.released": ResourceData(device="desktop:gpu0", released_stage="score"),
    "plan.ready": PlanReadyData(queries=[Query(id="q0", text="q")]),
    "hit.found": HitFoundData(url="https://x.test", title="X", query_ids=["q0"]),
    "page.fetched": PageFetchedData(url="https://x.test", source_id="s", title="X", chars=10, cached=True),
    "page.failed": PageFailedData(url="https://y.test", reason="404"),
    "passages.scored": PassagesScoredData(
        query_id="q0", scorer="jev", scored=3, kept=1, threshold_display=0.5, passages=[PASSAGE]
    ),
    "round.done": RoundDoneData(round=1, query_ids=["q1"], new_pages=4, known_pages=1, kept=3),
    "gap.ready": GapReadyData(
        round=1, queries=[Query(id="q4", text="f", round=2)], note="n", uncovered=[], retried=False
    ),
    "research.done": ResearchDoneData(planned=3, ran=2, reason="no new sources", note="n"),
    "report.delta": ReportTextData(text="Intro"),
    "report.snapshot": ReportTextData(text="Intro"),
}


def test_stage_order() -> None:
    assert STAGES == ("load", "plan", "search", "fetch", "chunk", "prefilter", "score", "gap", "select", "write")
    assert get_args(Stage) == STAGES


def test_every_event_type_has_sample() -> None:
    assert {event.model_fields["type"].default for event in EVENT_TYPES} == set(DATA)


@pytest.mark.parametrize("event_type", list(DATA))
def test_event_round_trip(event_type: str) -> None:
    stage = "score" if event_type.startswith(("stage.", "resource.", "passages.")) else None
    event = make_event(7, "run", TS, event_type, stage, DATA[event_type])
    line = event.model_dump_json()
    assert parse_event(line) == event
    assert {"seq", "run_id", "ts", "type", "data"} <= set(json.loads(line))


def test_unknown_event_type_rejected() -> None:
    line = json.dumps({"seq": 1, "run_id": "r", "ts": TS.isoformat(), "type": "stage.paused", "data": {}})
    with pytest.raises(ValidationError):
        parse_event(line)


def test_stage_omitted_when_none() -> None:
    event = make_event(1, "r", TS, "run.failed", None, DATA["run.failed"])
    assert "stage" not in json.loads(event.model_dump_json())
    with_stage = make_event(2, "r", TS, "stage.done", "plan", DATA["stage.done"])
    assert json.loads(with_stage.model_dump_json())["stage"] == "plan"


def test_run_contracts_round_trip() -> None:
    request = RunRequest(query="q", sources="web", until="select", attachments=["notes.md"])
    record = RunRecord(
        run_id="r",
        created_at=TS,
        request=request,
        profile="workstation",
        overrides=["write.tone=critical"],
        settings={"score": {"api_key": "***"}},
        parent_run_id="p",
        fork_from="write",
        version=2,
        origin="api",
        token_name="ci-runner",
    )
    output = RunOutput(
        run_id="r",
        status="done",
        run_dir="/runs/r",
        context=Context(query="q", passages=[], sources=[], budget_tokens=10, used_tokens=0),
    )
    for value in (request, record, output):
        assert type(value).model_validate_json(value.model_dump_json()) == value


def test_record_without_origin_reads_as_web() -> None:
    data = {"run_id": "r", "created_at": TS.isoformat(), "request": {"query": "q"}, "profile": "p", "settings": {}}
    record = RunRecord.model_validate(data)
    assert (record.origin, record.token_name) == ("web", None)


def test_empty_query_rejected() -> None:
    with pytest.raises(ValidationError, match="query"):
        RunRequest(query="")


def test_schema_covers_events() -> None:
    definitions = json.loads(CliRunner().invoke(app, ["schema"]).output)["$defs"]
    assert {event.__name__ for event in EVENT_TYPES} | {"RunOutput", "RunRecord"} <= set(definitions)


def test_run_config_defaults_and_override() -> None:
    run = Settings().run
    assert (run.runs_dir, run.cache_dir, run.page_cache_ttl_hours) == (None, None, 24)
    assert run.stage_timeouts == DEFAULT_STAGE_TIMEOUTS
    assert run.stage_timeouts["write"] == 1800
    changed = resolve("workstation", ["run.stage_timeouts.score=30"], {"XDG_CONFIG_HOME": "/nonexistent"}).run
    assert changed.stage_timeouts["score"] == 30
    assert changed.stage_timeouts["fetch"] == 600


def test_restore_secrets() -> None:
    env = {"XDG_CONFIG_HOME": "/nonexistent", "WOSARCHER_SCORE__API_KEY": "sk-score"}
    saved = redact(resolve("workstation", ["score.top_k=7"], env))
    assert saved["score"]["api_key"] == "***"
    current = resolve("workstation", [], env)
    restored, dropped = restore_secrets(saved, current)
    assert dropped == []
    assert restored.score.api_key is not None
    assert restored.score.api_key.get_secret_value() == "sk-score"
    assert restored.score.top_k == 7
    assert restore_secrets(saved, current, ["write.tone=critical"])[0].write.tone == "critical"


def test_ledger_total_and_rows() -> None:
    ledger = UsageLedger({})
    ledger.record("llm", "plan", input_tokens=100, output_tokens=5)
    ledger.record("llm", "write", input_tokens=10)
    ledger.record("firecrawl", "fetch", units=2)
    total = ledger.total()
    assert (total.requests, total.input_tokens, total.output_tokens, total.units) == (3, 110, 5, 2)
    rows = {(row.provider, row.stage): row.usage for row in ledger.rows()}
    assert set(rows) == {("llm", "plan"), ("llm", "write"), ("firecrawl", "fetch")}
    assert rows["llm", "plan"].input_tokens == 100
    assert rows["llm", "plan"].cost == 0

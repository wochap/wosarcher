import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from wosarcher.cli import app
from wosarcher.models import (
    ApiError,
    Contract,
    ForkCreate,
    LLMPatch,
    LoginError,
    LoginRequest,
    ModelInfo,
    ProfileInfo,
    ProviderEntryInfo,
    ProvidersReport,
    RunCosts,
    RunCreate,
    RunCreated,
    RunDetail,
    RunRecord,
    RunRequest,
    RunSummary,
    ServerSettings,
    SessionInfo,
    TokenCreate,
    TokenCreated,
    TokenInfo,
    UsageTotals,
    WritingOptions,
    WritingPatch,
)

TS = datetime(2026, 1, 1, tzinfo=UTC)
SUMMARY = {
    "run_id": "r",
    "query": "q",
    "status": "done",
    "created": TS,
    "profile": "workstation",
    "writing": WritingOptions(tone="critical"),
    "duration_s": 125.0,
    "cost": 0.012,
}
EXAMPLES: list[Contract] = [
    RunCreate(query="q", sources="web", until="select", writing=WritingPatch(words=600), set=["score.top_k=5"]),
    RunCreate(query="q", use={"score": "jev-strict"}, llm=LLMPatch(model="m", context_window=262144)),
    ForkCreate(from_stage="write", writing=WritingPatch(tone="critical"), profile="cloud", use={"llm": "agents"}),
    RunCreated(run_id="r", status="queued"),
    RunSummary.model_validate(SUMMARY),
    RunDetail.model_validate(
        {
            **SUMMARY,
            "request": RunRecord(
                run_id="r", created_at=TS, request=RunRequest(query="q"), profile="workstation", settings={}
            ),
            "costs": RunCosts(stages={}, providers={}, total=UsageTotals(cost=0.012)),
            "last_seq": 7,
        }
    ),
    ServerSettings(writing=WritingOptions(words=800), sources="web"),
    ProfileInfo(name="cloud", active=True, description="Hosted APIs.", use={"score": "bm25"}, context_tokens="auto"),
    ProvidersReport(
        profile="cloud",
        gpu_policy="exclusive",
        entries=[
            ProviderEntryInfo(
                block="search",
                name="searxng",
                source="user",
                provider="searxng",
                release="llama-swap",
                status="degraded",
                latency_ms=1840,
                detail="slow",
            ),
            ProviderEntryInfo(
                block="llm",
                name="agents",
                source="user",
                model="qwen3-14b",
                models=[ModelInfo(id="qwen3-14b", context_window=32768, max_output_tokens=8192)],
            ),
        ],
        warnings=["w"],
    ),
    ApiError(error="run_not_found", detail="no run r"),
    LoginRequest(password="hunter22"),
    SessionInfo(method="cookie", since=TS, expires=TS),
    SessionInfo(method="token", token_name="laptop"),
    TokenInfo(id="a1b2c3d4", name="laptop", masked="wosarcher_••••k9Qz", created=TS, last_used=TS),
    TokenCreate(name="laptop"),
    TokenCreated(id="a1b2c3d4", name="laptop", token="wosarcher_" + "a" * 36),
    LoginError(error="wrong_password", detail="wrong password", attempts_left=4),
    LoginError(error="rate_limited", detail="too many attempts", retry_after=30),
]


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: type(example).__name__)
def test_api_models_round_trip(example: Contract) -> None:
    assert type(example).model_validate_json(example.model_dump_json()) == example


def test_fork_create_uses_from() -> None:
    fork = ForkCreate.model_validate({"from": "write"})
    assert fork.from_stage == "write"
    assert json.loads(fork.model_dump_json())["from"] == "write"


def test_writing_patch_names_field() -> None:
    with pytest.raises(ValidationError) as error:
        RunCreate.model_validate({"query": "q", "writing": {"words": 0}})
    assert error.value.errors()[0]["loc"] == ("writing", "words")


def test_schema_has_api_models() -> None:
    definitions = json.loads(CliRunner().invoke(app, ["schema"]).output)["$defs"]
    names = {"RunCreate", "ForkCreate", "RunCreated", "RunSummary", "RunDetail", "ServerSettings"}
    assert names | {"ProfileInfo", "ProviderEntryInfo", "ProvidersReport", "ApiError", "RunNotActive"} <= set(
        definitions
    )


def test_use_names_a_block() -> None:
    with pytest.raises(ValidationError, match=r"use\.scorer is not a block"):
        RunCreate.model_validate({"query": "q", "use": {"scorer": "bm25"}})


def test_budgets_are_llm_fields() -> None:
    with pytest.raises(ValidationError) as error:
        RunCreate.model_validate({"query": "q", "research": {"context_tokens": "auto"}})
    assert error.value.errors()[0]["loc"] == ("research", "context_tokens")
    assert (
        RunCreate.model_validate({"query": "q", "llm": {"gap_context_tokens": "auto"}}).llm.gap_context_tokens == "auto"
    )


def test_schema_has_auth_models() -> None:
    definitions = json.loads(CliRunner().invoke(app, ["schema"]).output)["$defs"]
    names = {"LoginRequest", "SessionInfo", "TokenInfo", "TokenCreate", "TokenCreated", "LoginError"}
    assert names <= set(definitions)

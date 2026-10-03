import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from tests.adapters.conftest import chunks
from wosarcher.adapters.bm25 import Bm25Scorer
from wosarcher.adapters.embeddings import OpenAIEmbedder
from wosarcher.adapters.firecrawl import FirecrawlFetcher
from wosarcher.adapters.jev import JevScorer
from wosarcher.adapters.llm import ChatLLM
from wosarcher.adapters.passthrough import PassthroughScorer
from wosarcher.adapters.rerank import RerankScorer
from wosarcher.adapters.searxng import SearxngSearcher
from wosarcher.build import build
from wosarcher.config import Settings, resolve
from wosarcher.http import UsageLedger
from wosarcher.models import Message, Query


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def settings(tmp_path: Path, profile: str = "workstation", *overrides: str) -> Settings:
    return resolve(profile, list(overrides), {"XDG_CONFIG_HOME": str(tmp_path)})


async def test_build_workstation_profile(tmp_path: Path, http: httpx.AsyncClient) -> None:
    adapters = build(settings(tmp_path), http, UsageLedger({}))
    assert isinstance(adapters.searcher, SearxngSearcher)
    assert isinstance(adapters.fetcher, FirecrawlFetcher)
    assert isinstance(adapters.embedder, OpenAIEmbedder)
    assert isinstance(adapters.scorers["rerank"], RerankScorer)
    assert isinstance(adapters.planner, ChatLLM)
    assert isinstance(adapters.writer, ChatLLM)
    assert set(adapters.managed) == {"search", "fetch", "prefilter", "score", "llm"}


async def test_unknown_provider_names_allowed_values(tmp_path: Path, http: httpx.AsyncClient) -> None:
    with pytest.raises(ValueError, match=r"score\.provider 'x' is not one of: rerank, jev, bm25"):
        build(settings(tmp_path, "workstation", "score.provider=x"), http, UsageLedger({}))


async def test_bm25_prefilter_has_no_embedder(tmp_path: Path, http: httpx.AsyncClient) -> None:
    adapters = build(settings(tmp_path, "cloud"), http, UsageLedger({}))
    assert adapters.embedder is None
    assert "prefilter" not in adapters.managed


async def test_none_prefilter_has_no_embedder(tmp_path: Path, http: httpx.AsyncClient) -> None:
    adapters = build(settings(tmp_path, "workstation", "prefilter.provider=none"), http, UsageLedger({}))
    assert adapters.embedder is None


async def test_scorers_in_fallback_order(tmp_path: Path, http: httpx.AsyncClient) -> None:
    scorers = build(settings(tmp_path, "cloud"), http, UsageLedger({})).scorers
    assert list(scorers) == ["jev", "bm25", "passthrough"]
    assert isinstance(scorers["jev"], JevScorer)
    assert isinstance(scorers["bm25"], Bm25Scorer)
    assert isinstance(scorers["passthrough"], PassthroughScorer)


@respx.mock
async def test_jev_default_concurrency_64(http: httpx.AsyncClient) -> None:
    in_flight = 0
    peak = 0

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json={"answers": {"usefulness": {"score": 1.0}}})

    respx.post("https://api.typesafe.ai/v1/systemone").mock(side_effect=slow)
    cfg = Settings.model_validate({"score": {"provider": "jev", "base_url": "https://api.typesafe.ai/v1"}})
    scorer = build(cfg, http, UsageLedger({})).scorers["jev"]
    await scorer.score(Query(query_id="q", text="x"), chunks(*(str(i) for i in range(100))))
    assert peak == 64


LLM_URL = "http://localhost:8080/v1/chat/completions"
REPLY = {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 100, "completion_tokens": 1}}


@respx.mock
async def test_planner_writer_share_client(tmp_path: Path, http: httpx.AsyncClient) -> None:
    in_flight = 0
    peak = 0

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return httpx.Response(200, json=REPLY)

    respx.post(LLM_URL).mock(side_effect=slow)
    adapters = build(settings(tmp_path), http, UsageLedger({}))
    messages = [Message(role="user", content="hi")]
    await asyncio.gather(
        adapters.planner.complete(messages, max_tokens=4), adapters.writer.complete(messages, max_tokens=4)
    )
    assert peak == 1


@respx.mock
async def test_planner_and_writer_usage_separate(tmp_path: Path, http: httpx.AsyncClient) -> None:
    respx.post(LLM_URL).mock(
        side_effect=[
            httpx.Response(200, json={**REPLY, "usage": {"prompt_tokens": 100}}),
            httpx.Response(200, json={**REPLY, "usage": {"prompt_tokens": 900}}),
        ]
    )
    ledger = UsageLedger({})
    adapters = build(settings(tmp_path), http, ledger)
    messages = [Message(role="user", content="hi")]
    await adapters.planner.complete(messages, max_tokens=4)
    await adapters.writer.complete(messages, max_tokens=4)
    assert ledger.totals[("llm", "plan")].input_tokens == 100
    assert ledger.totals[("llm", "write")].input_tokens == 900

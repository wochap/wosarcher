import json
import tomllib
from importlib.resources import files

import httpx
import pytest
import respx

from tests.adapters.conftest import chunks, provider_client
from wosarcher.adapters.jev import JevScorer
from wosarcher.config import ScoreConfig
from wosarcher.http import ProviderError, UsageLedger
from wosarcher.models import Query

BASE = "https://api.typesafe.ai/v1"
Q = Query(id="q1", text="How are batteries recycled?")


def scorer(http: httpx.AsyncClient, ledger: UsageLedger, **fields: object) -> JevScorer:
    cfg = ScoreConfig.model_validate({"provider": "jev", "base_url": BASE, **fields})
    return JevScorer(cfg, provider_client(cfg, http, ledger), ledger)


def answer(score: object, tokens: int = 0) -> dict[str, object]:
    return {"answers": {"usefulness": {"score": score}}, "usage": {"input_tokens": tokens}}


def test_prompt_file_has_four_criteria() -> None:
    prompt = tomllib.loads(files("wosarcher").joinpath("prompts", "jev.toml").read_text(encoding="utf-8"))
    assert len(prompt["criteria"]) == 4
    assert "$query" in prompt["instructions"]


@respx.mock
async def test_calibrated_score(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/systemone").respond(200, json=answer(2.4))
    adapter = scorer(http, ledger)
    scores = await adapter.score(Q, chunks("Batteries are shredded."))
    assert [(score.value, score.scorer) for score in scores] == [(2.4, "jev")]
    assert adapter.calibrated is True
    body = json.loads(route.calls.last.request.content)
    question = body["questions"]["usefulness"]
    assert body["model"] == "jev-latest"
    assert question["type"] == "score"
    assert question["instructions"].endswith("How are batteries recycled?")
    assert len(question["criteria"]) == 4


@respx.mock
async def test_scraped_text_not_templated(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/systemone").respond(200, json=answer(1.0))
    text = "costs $query and {query} and $$"
    await scorer(http, ledger).score(Q, chunks(text))
    assert json.loads(route.calls.last.request.content)["state"] == text


@respx.mock
async def test_bad_answer(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/systemone").respond(200, json={"answers": {}})
    with pytest.raises(ProviderError, match=r"^jev: "):
        await scorer(http, ledger).score(Q, chunks("a"))


@respx.mock
async def test_out_of_range_score(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/systemone").respond(200, json=answer(3.5))
    with pytest.raises(ProviderError, match="outside 0 to 3"):
        await scorer(http, ledger).score(Q, chunks("a"))


@respx.mock
async def test_input_tokens_recorded(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/systemone").respond(200, json=answer(1.0, tokens=120))
    await scorer(http, ledger).score(Q, chunks("a", "b"))
    usage = ledger.totals[("jev", "score")]
    assert (usage.requests, usage.input_tokens) == (2, 240)


@respx.mock
async def test_probe_ok(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/systemone").respond(200, json=answer(0.0))
    health = await scorer(http, ledger).probe()
    assert (health.block, health.status, health.model, health.unload) == ("score", "ok", "jev-latest", "n/a")

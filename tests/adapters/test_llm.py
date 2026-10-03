import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from tests.adapters.conftest import provider_client
from wosarcher.adapters.llm import ChatLLM
from wosarcher.config import LLMConfig
from wosarcher.http import ProviderError, UsageLedger
from wosarcher.models import Message

BASE = "http://localhost:8080/v1"
MESSAGES = [Message(role="system", content="Plan."), Message(role="user", content="Batteries?")]


def llm(http: httpx.AsyncClient, ledger: UsageLedger, **fields: object) -> ChatLLM:
    cfg = LLMConfig.model_validate({"provider": "llm", "base_url": BASE, **fields})
    return ChatLLM(cfg, provider_client(cfg, http, ledger), ledger, "plan")


def chat(content: str | None, **extra: object) -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}], **extra}


def sse(*events: object) -> bytes:
    lines = [f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n" for event in events]
    return "".join(lines).encode()


def delta(text: str) -> dict[str, object]:
    return {"choices": [{"delta": {"content": text}}]}


@respx.mock
async def test_completion_returned(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    usage = {"prompt_tokens": 120, "completion_tokens": 30}
    route = respx.post(f"{BASE}/chat/completions").respond(200, json=chat("Plan: ...", usage=usage))
    completion = await llm(http, ledger, model="writer").complete(MESSAGES, max_tokens=64)
    assert (completion.text, completion.input_tokens, completion.output_tokens) == ("Plan: ...", 120, 30)
    assert json.loads(route.calls.last.request.content) == {
        "messages": [{"role": "system", "content": "Plan."}, {"role": "user", "content": "Batteries?"}],
        "max_tokens": 64,
        "stream": False,
        "model": "writer",
    }
    assert ledger.totals[("llm", "plan")].output_tokens == 30


@respx.mock
async def test_null_content(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, json=chat(None))
    assert (await llm(http, ledger).complete(MESSAGES, max_tokens=8)).text == ""


@respx.mock
async def test_deltas_in_order(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    usage: dict[str, object] = {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}}
    route = respx.post(f"{BASE}/chat/completions").respond(
        200, content=sse(delta("Hel"), delta("lo"), delta(""), usage, "[DONE]")
    )
    assert [text async for text in llm(http, ledger).stream(MESSAGES, max_tokens=8)] == ["Hel", "lo"]
    body = json.loads(route.calls.last.request.content)
    assert (body["stream"], body["stream_options"]) == (True, {"include_usage": True})
    totals = ledger.totals[("llm", "plan")]
    assert (totals.requests, totals.input_tokens, totals.output_tokens) == (1, 7, 2)


@respx.mock
async def test_error_mid_stream(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    async def broken() -> AsyncIterator[bytes]:
        yield sse(delta("Hel"))
        raise httpx.ReadError("connection dropped")

    route = respx.post(f"{BASE}/chat/completions").respond(200, stream=broken())  # pyright: ignore[reportArgumentType]
    stream = llm(http, ledger).stream(MESSAGES, max_tokens=8)
    assert await anext(stream) == "Hel"
    with pytest.raises(ProviderError, match="during stream"):
        await anext(stream)
    assert route.call_count == 1


@respx.mock
async def test_consumer_stops_early(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, content=sse(delta("a"), delta("b"), "[DONE]"))
    respx.post(f"{BASE}/other").respond(200, json={})
    adapter = llm(http, ledger, concurrency=1)
    stream = adapter.stream(MESSAGES, max_tokens=8)
    assert await anext(stream) == "a"
    await stream.aclose()
    assert await adapter.client.post_json("/other", {}) == {}
    assert ledger.totals[("llm", "plan")].requests == 1


@respx.mock
async def test_probe_reports_model(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, json=chat("OK", model="qwen3-8b-q4_k_m"))
    health = await llm(http, ledger, model="writer").probe()
    assert (health.block, health.status, health.model) == ("llm", "ok", "qwen3-8b-q4_k_m")


@respx.mock
async def test_release_none_sends_nothing(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    await llm(http, ledger).release()
    assert respx.calls.call_count == 0

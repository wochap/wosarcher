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


def chat(content: str | None, finish_reason: str = "stop", **extra: object) -> dict[str, object]:
    message = {"role": "assistant", "content": content}
    return {"choices": [{"message": message, "finish_reason": finish_reason}], **extra}


def sse(*events: object) -> bytes:
    lines = [f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n" for event in events]
    return "".join(lines).encode()


def delta(text: str, finish_reason: str | None = None) -> dict[str, object]:
    return {"choices": [{"delta": {"content": text}, "finish_reason": finish_reason}]}


@respx.mock
async def test_completion_returned(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    usage = {"prompt_tokens": 120, "completion_tokens": 30}
    route = respx.post(f"{BASE}/chat/completions").respond(200, json=chat("Plan: ...", usage=usage))
    completion = await llm(http, ledger, model="writer").complete(MESSAGES, max_tokens=64)
    assert (completion.text, completion.input_tokens, completion.output_tokens) == ("Plan: ...", 120, 30)
    assert json.loads(route.calls.last.request.content) == {
        "messages": [{"role": "system", "content": "Plan."}, {"role": "user", "content": "Batteries?"}],
        "max_completion_tokens": 64,
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
    respx.get(url__regex=r"/props$").respond(404)
    health = await llm(http, ledger, model="writer").probe()
    assert (health.block, health.status, health.model) == ("llm", "ok", "qwen3-8b-q4_k_m")


@respx.mock
async def test_release_none_sends_nothing(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    await llm(http, ledger).release()
    assert respx.calls.call_count == 0


@respx.mock
async def test_default_limit_field(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/chat/completions").respond(200, json=chat("ok"))
    await llm(http, ledger).complete(MESSAGES, max_tokens=512)
    body = json.loads(route.calls.last.request.content)
    assert body["max_completion_tokens"] == 512
    assert "max_tokens" not in body


@respx.mock
async def test_legacy_limit_field(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/chat/completions").respond(200, json=chat("ok"))
    await llm(http, ledger, max_tokens_field="max_tokens").complete(MESSAGES, max_tokens=512)
    body = json.loads(route.calls.last.request.content)
    assert body["max_tokens"] == 512
    assert "max_completion_tokens" not in body


@respx.mock
async def test_reasoning_tokens_added(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    route = respx.post(f"{BASE}/chat/completions").respond(200, json=chat("ok"))
    await llm(http, ledger, reasoning_tokens=4096).complete(MESSAGES, max_tokens=512)
    assert json.loads(route.calls.last.request.content)["max_completion_tokens"] == 4608


@respx.mock
async def test_empty_content_at_length_fails(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, json=chat("", finish_reason="length"))
    with pytest.raises(ProviderError, match=r"llm\.reasoning_tokens"):
        await llm(http, ledger).complete(MESSAGES, max_tokens=512)


@respx.mock
async def test_empty_content_on_stop_ok(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, json=chat(""))
    assert (await llm(http, ledger).complete(MESSAGES, max_tokens=512)).text == ""


@respx.mock
async def test_finish_reason_reported(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(
        200, content=sse(delta("Hel"), delta("lo", "length"), {"choices": [], "usage": {}}, "[DONE]")
    )
    seen: list[object] = []
    async for text in llm(http, ledger).stream(MESSAGES, max_tokens=8, on_finish=lambda r: seen.append(("finish", r))):
        seen.append(text)
    assert seen == ["Hel", "lo", ("finish", "length")]


@respx.mock
async def test_finish_reason_missing(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, content=sse(delta("Hi"), "[DONE]"))
    reasons: list[str | None] = []
    assert [text async for text in llm(http, ledger).stream(MESSAGES, max_tokens=8, on_finish=reasons.append)] == ["Hi"]
    assert reasons == [None]


@respx.mock
async def test_error_event_mid_stream(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    error = {"error": {"message": "the request exceeds the available context size", "code": 400}}
    respx.post(f"{BASE}/chat/completions").respond(200, content=sse(delta("a"), delta("b"), error))
    stream = llm(http, ledger).stream(MESSAGES, max_tokens=8)
    assert [await anext(stream), await anext(stream)] == ["a", "b"]
    with pytest.raises(ProviderError, match="exceeds the available context size"):
        await anext(stream)


@respx.mock
async def test_error_event_string(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, content=sse({"error": "boom"}))
    with pytest.raises(ProviderError, match="boom"):
        _ = [text async for text in llm(http, ledger).stream(MESSAGES, max_tokens=8)]


@respx.mock
async def test_stream_no_text_at_length_fails(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(
        200, content=sse({"choices": [], "usage": {}}, delta("", "length"), "[DONE]")
    )
    with pytest.raises(ProviderError, match=r"llm\.reasoning_tokens"):
        _ = [text async for text in llm(http, ledger).stream(MESSAGES, max_tokens=8)]


@respx.mock
async def test_stream_text_at_length_ok(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, content=sse(delta("a"), delta("", "length"), "[DONE]"))
    reasons: list[str | None] = []
    assert [text async for text in llm(http, ledger).stream(MESSAGES, max_tokens=8, on_finish=reasons.append)] == ["a"]
    assert reasons == ["length"]


@respx.mock
async def test_probe_reads_props(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, json=chat("OK"))
    respx.get("http://localhost:8080/props").respond(200, json={"default_generation_settings": {"n_ctx": 4096}})
    health = await llm(http, ledger).probe()
    assert (health.context_window, health.note) == (4096, "server context 4096 tokens")


@respx.mock
async def test_probe_props_via_llama_swap(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, json=chat("OK"))
    respx.get("http://localhost:8080/props").respond(404)
    respx.get("http://localhost:8080/upstream/writer/props").respond(200, json={"n_ctx": 8192})
    assert (await llm(http, ledger, model="writer").probe()).context_window == 8192


@respx.mock
async def test_probe_without_props(http: httpx.AsyncClient, ledger: UsageLedger) -> None:
    respx.post(f"{BASE}/chat/completions").respond(200, json=chat("OK"))
    respx.get("http://localhost:8080/props").respond(404)
    respx.get("http://localhost:8080/upstream/writer/props").respond(404)
    health = await llm(http, ledger, model="writer").probe()
    assert (health.status, health.context_window, health.note) == ("ok", None, None)

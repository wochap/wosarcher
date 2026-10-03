"""LLM: an OpenAI-compatible chat endpoint (`POST <base_url>/chat/completions`), complete and streaming."""

import json
from collections.abc import AsyncGenerator
from typing import Any

from wosarcher.config import LLMConfig
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, probe, unload
from wosarcher.models import Completion, Message, ProviderHealth


class ChatLLM:
    def __init__(self, cfg: LLMConfig, client: ProviderClient, ledger: UsageLedger, stage: str) -> None:
        self.cfg = cfg
        self.client = client
        self.ledger = ledger
        self.stage = stage

    def body(self, messages: list[Message], max_tokens: int, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if self.cfg.model:
            body["model"] = self.cfg.model
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    async def _complete(self, messages: list[Message], max_tokens: int) -> tuple[Completion, str | None]:
        data = await self.client.post_json("/chat/completions", self.body(messages, max_tokens, stream=False))
        usage: dict[str, Any] = data.get("usage") or {}
        completion = Completion(
            text=self._content(data),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )
        self.ledger.record(
            self.cfg.provider,
            self.stage,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )
        return completion, data.get("model")

    def _content(self, data: Any) -> str:
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError(self.cfg.provider, "answer has no `choices[0].message`") from None

    async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion:
        return (await self._complete(messages, max_tokens))[0]

    async def stream(self, messages: list[Message], *, max_tokens: int) -> AsyncGenerator[str]:
        usage: dict[str, Any] = {}
        lines = self.client.stream_lines("/chat/completions", self.body(messages, max_tokens, stream=True))
        try:
            async for line in lines:
                if line == "[DONE]":
                    break
                try:
                    event = json.loads(line)
                except ValueError:
                    raise ProviderError(self.cfg.provider, f"invalid stream event: {line[:200]}") from None
                usage = event.get("usage") or usage
                choices: list[dict[str, Any]] = event.get("choices") or []
                delta: dict[str, Any] = (choices[0].get("delta") or {}) if choices else {}
                if text := delta.get("content"):
                    yield text
        finally:
            await lines.aclose()
            self.ledger.record(
                self.cfg.provider,
                self.stage,
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            )

    async def probe(self) -> ProviderHealth:
        async def call() -> str | None:
            return (await self._complete([Message(role="user", content="Say OK.")], 1))[1]

        return await probe(self.client, "llm", call)

    async def release(self) -> None:
        await unload(self.client, self.cfg.release, self.cfg.model)

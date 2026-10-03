"""LLM: an OpenAI-compatible chat endpoint (`POST <base_url>/chat/completions`), complete and streaming."""

import json
from collections.abc import AsyncGenerator, Callable
from typing import Any, cast

from wosarcher.config import LLMConfig
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, probe, unload
from wosarcher.models import Completion, Message, ProviderHealth


def ignore(_reason: str | None) -> None:
    pass


class ChatLLM:
    def __init__(self, cfg: LLMConfig, client: ProviderClient, ledger: UsageLedger, stage: str) -> None:
        self.cfg = cfg
        self.client = client
        self.ledger = ledger
        self.stage = stage

    def body(self, messages: list[Message], max_tokens: int, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            self.cfg.max_tokens_field: max_tokens + self.cfg.reasoning_tokens,
            "stream": stream,
        }
        if self.cfg.model:
            body["model"] = self.cfg.model
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    async def _complete(self, messages: list[Message], max_tokens: int) -> tuple[Completion, str | None]:
        body = self.body(messages, max_tokens, stream=False)
        data = await self.client.post_json("/chat/completions", body)
        usage: dict[str, Any] = data.get("usage") or {}
        text = self._content(data)
        if not text and data["choices"][0].get("finish_reason") == "length":
            raise self.spent(body[self.cfg.max_tokens_field])
        completion = Completion(
            text=text,
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

    def spent(self, limit: int) -> ProviderError:
        return ProviderError(
            self.cfg.provider,
            f"the model spent the whole output limit of {limit} tokens without writing text; "
            "raise llm.reasoning_tokens (reasoning models count hidden reasoning tokens)",
        )

    def stream_error(self, error: Any) -> ProviderError:
        message = cast("dict[str, Any]", error).get("message") if isinstance(error, dict) else None
        text = message if isinstance(message, str) else str(cast("object", error))
        return ProviderError(self.cfg.provider, f"stream error: {text[:200]}")

    async def complete(self, messages: list[Message], *, max_tokens: int) -> Completion:
        return (await self._complete(messages, max_tokens))[0]

    async def stream(
        self, messages: list[Message], *, max_tokens: int, on_finish: Callable[[str | None], None] = ignore
    ) -> AsyncGenerator[str]:
        usage: dict[str, Any] = {}
        reason: str | None = None
        wrote = False
        body = self.body(messages, max_tokens, stream=True)
        lines = self.client.stream_lines("/chat/completions", body)
        try:
            async for line in lines:
                if line == "[DONE]":
                    break
                try:
                    event = json.loads(line)
                except ValueError:
                    raise ProviderError(self.cfg.provider, f"invalid stream event: {line[:200]}") from None
                if "error" in event:
                    raise self.stream_error(event["error"])
                usage = event.get("usage") or usage
                choices: list[dict[str, Any]] = event.get("choices") or []
                delta: dict[str, Any] = (choices[0].get("delta") or {}) if choices else {}
                reason = (choices[0].get("finish_reason") if choices else None) or reason
                if text := delta.get("content"):
                    wrote = True
                    yield text
            if reason == "length" and not wrote:
                raise self.spent(body[self.cfg.max_tokens_field])
            on_finish(reason)
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

        health = await probe(self.client, "llm", call)
        if health.status != "ok" or not (size := await self.server_context()):
            return health
        return health.model_copy(update={"context_window": size, "note": f"server context {size} tokens"})

    async def server_context(self) -> int | None:
        """The server's `n_ctx` from llama-server `/props` (directly or behind llama-swap), if it has one."""
        paths = ["/props", *([f"/upstream/{self.cfg.model}/props"] if self.cfg.model else [])]
        for path in paths:
            try:
                data = await self.client.get_json(path, root=True)
            except ProviderError:
                continue
            if not isinstance(data, dict):
                continue
            props = cast("dict[str, Any]", data)
            settings = props.get("default_generation_settings")
            size = cast("dict[str, Any]", settings).get("n_ctx") if isinstance(settings, dict) else props.get("n_ctx")
            if isinstance(size, int) and not isinstance(size, bool) and size > 0:
                return size
        return None

    async def release(self) -> None:
        await unload(self.client, self.cfg.release, self.cfg.model)

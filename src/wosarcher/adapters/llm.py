"""LLM: an OpenAI-compatible chat endpoint (`POST <base_url>/chat/completions`), complete and streaming."""

import json
from collections.abc import AsyncGenerator, Callable
from typing import Any, cast

from wosarcher.config import LLMConfig
from wosarcher.http import ProviderClient, ProviderError, UsageLedger, probe, unload
from wosarcher.models import Completion, Effort, Message, ProviderHealth


def ignore(_reason: str | None) -> None:
    pass


async def prepend(first: str | None, rest: AsyncGenerator[str]) -> AsyncGenerator[str]:
    if first is None:
        return
    yield first
    async for line in rest:
        yield line


class ChatLLM:
    """`stage` names the ledger stage and the `llm.reasoning.<stage>` step in error text."""

    def __init__(self, cfg: LLMConfig, client: ProviderClient, ledger: UsageLedger, stage: str) -> None:
        self.cfg = cfg
        self.client = client
        self.ledger = ledger
        self.stage = stage

    def body(self, messages: list[Message], max_tokens: int, effort: Effort, *, stream: bool) -> dict[str, Any]:
        """`none`: exact cap and no reasoning; a level: no cap, the server budgets; `default`: neither field."""
        body: dict[str, Any] = {
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "stream": stream,
        }
        if effort != "default":
            body["reasoning_effort"] = effort
        if effort == "none":
            body[self.cfg.max_tokens_field] = max_tokens
        if self.cfg.model:
            body["model"] = self.cfg.model
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    async def _complete(
        self, messages: list[Message], max_tokens: int, effort: Effort
    ) -> tuple[Completion, str | None]:
        body = self.body(messages, max_tokens, effort, stream=False)
        try:
            data = await self.client.post_json("/chat/completions", body)
        except ProviderError as error:
            raise self.rejected(error) from None
        usage: dict[str, Any] = data.get("usage") or {}
        text = self._content(data)
        if not text and data["choices"][0].get("finish_reason") == "length":
            raise self.spent(body.get(self.cfg.max_tokens_field))
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

    def spent(self, limit: int | None) -> ProviderError:
        cap = f" of {limit} tokens" if limit is not None else ""
        return ProviderError(
            self.cfg.provider,
            f"the model spent the whole output limit{cap} without writing text; "
            f"set llm.reasoning.{self.stage} to none (hidden reasoning counts against the limit)",
        )

    def rejected(self, error: ProviderError) -> ProviderError:
        """A 400 naming `reasoning_effort` gets the hint to drop the field; other errors pass through."""
        if error.status != 400 or "reasoning_effort" not in str(error):
            return error
        return ProviderError(
            self.cfg.provider,
            f'the server rejects reasoning_effort; set llm.reasoning.{self.stage} = "default" ({error})',
            url=error.url,
            status=error.status,
        )

    def stream_error(self, error: Any) -> ProviderError:
        message = cast("dict[str, Any]", error).get("message") if isinstance(error, dict) else None
        text = message if isinstance(message, str) else str(cast("object", error))
        return ProviderError(self.cfg.provider, f"stream error: {text[:200]}")

    async def complete(self, messages: list[Message], *, max_tokens: int, effort: Effort) -> Completion:
        return (await self._complete(messages, max_tokens, effort))[0]

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int,
        effort: Effort,
        on_finish: Callable[[str | None], None] = ignore,
    ) -> AsyncGenerator[str]:
        usage: dict[str, Any] = {}
        reason: str | None = None
        wrote = False
        body = self.body(messages, max_tokens, effort, stream=True)
        lines = self.client.stream_lines("/chat/completions", body)
        try:
            try:
                first = await anext(lines, None)
            except ProviderError as error:
                raise self.rejected(error) from None
            async for line in prepend(first, lines):
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
                raise self.spent(body.get(self.cfg.max_tokens_field))
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
            return (await self._complete([Message(role="user", content="Say OK.")], 1, "none"))[1]

        health = await probe(self.client, "llm", call)
        if health.status != "ok":
            return health
        notes: list[str] = []
        update: dict[str, Any] = {}
        if size := await self.server_context():
            update["context_window"] = size
            notes.append(f"server context {size} tokens")
        if listed := await self.models():
            notes.append(f"{len(listed)} models listed")
        if notes:
            update["note"] = "; ".join(notes)
        return health.model_copy(update=update)

    async def models(self) -> list[str]:
        """The model IDs `GET <base_url>/models` lists (`data[].id`); empty on any error or other shape."""
        try:
            data = await self.client.get_json("/models")
        except ProviderError:
            return []
        entries = cast("dict[str, Any]", data).get("data") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            return []
        ids = [
            cast("dict[str, Any]", entry).get("id") for entry in cast("list[Any]", entries) if isinstance(entry, dict)
        ]
        return [found for found in ids if isinstance(found, str) and found]

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

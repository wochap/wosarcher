"""Provider HTTP client (timeouts, retries, fallback URLs, concurrency) and usage recording."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import perf_counter
from typing import Any

import httpx

from wosarcher.config import DEFAULT_CONCURRENCY, Prices, Provider
from wosarcher.models import ProviderHealth

RETRY_STATUSES = {429, 502, 503, 504, 529}
MAX_RETRIES = 3


class ProviderError(Exception):
    def __init__(self, provider: str, message: str, *, url: str = "", status: int | None = None) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.url = url
        self.status = status


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    units: float = 0
    cost: float = 0


class UsageLedger:
    """Usage and cost summed per (provider, stage). Prices come from each provider block."""

    def __init__(self, prices: Mapping[str, Prices]) -> None:
        self.prices = prices
        self.totals: dict[tuple[str, str], Usage] = {}

    def record(
        self, provider: str, stage: str, *, input_tokens: int = 0, output_tokens: int = 0, units: float = 0
    ) -> None:
        usage = self.totals.setdefault((provider, stage), Usage())
        usage.requests += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.units += units
        prices = self.prices.get(provider, Prices())
        usage.cost += (
            input_tokens / 1e6 * (prices.input_per_mtok or 0)
            + output_tokens / 1e6 * (prices.output_per_mtok or 0)
            + units * (prices.per_unit or 0)
        )


def retry_delay(response: httpx.Response, attempt: int, backoff: float, cap: float) -> float:
    """`Retry-After` (seconds or HTTP date) when present, else exponential backoff; never above `cap`."""
    header = response.headers.get("retry-after")
    delay = backoff * 2**attempt
    if header:
        try:
            delay = float(header)
        except ValueError:
            with suppress(TypeError, ValueError):
                delay = (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds()
    return max(0.0, min(delay, cap))


def server_root(base_url: str) -> str:
    """`base_url` without a trailing `/`, then without a trailing `/v1`: where unload and health live."""
    return base_url.rstrip("/").removesuffix("/v1")


class ProviderClient:
    """One configured provider. Status errors stay on a URL; connection failures move to the next."""

    def __init__(
        self, name: str, cfg: Provider, http: httpx.AsyncClient, usage: UsageLedger, *, backoff: float = 0.5
    ) -> None:
        self.name = name
        self.cfg = cfg
        self.http = http
        self.usage = usage
        self.backoff = backoff
        self.slots = asyncio.Semaphore(cfg.concurrency or DEFAULT_CONCURRENCY.get(cfg.provider, 4))

    def excerpt(self, text: str) -> str:
        key = self.cfg.api_key.get_secret_value() if self.cfg.api_key else ""
        short = text[:200]
        return short.replace(key, "***") if key else short

    async def open(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        root: bool = False,
        stream: bool = False,
    ) -> httpx.Response:
        """Send until a 2xx response arrives; return it while still holding a concurrency slot."""
        headers = {"Authorization": f"Bearer {self.cfg.api_key.get_secret_value()}"} if self.cfg.api_key else {}
        timeout = httpx.Timeout(self.cfg.timeout, connect=self.cfg.connect_timeout)
        tried: list[str] = []
        for base in [self.cfg.base_url, *self.cfg.fallback_urls]:
            url = f"{server_root(base) if root else base.rstrip('/')}/{path.lstrip('/')}"
            tried.append(url)
            for attempt in range(MAX_RETRIES + 1):
                request = self.http.build_request(
                    method, url, json=json, params=params, headers=headers, timeout=timeout
                )
                await self.slots.acquire()
                try:
                    response = await self.http.send(request, stream=stream)
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    self.slots.release()
                    break
                except httpx.HTTPError as error:
                    self.slots.release()
                    raise ProviderError(self.name, f"{type(error).__name__} at {url}", url=url) from None
                except BaseException:
                    self.slots.release()
                    raise
                if response.status_code < 400:
                    return response
                try:
                    await response.aread()
                    await response.aclose()
                finally:
                    self.slots.release()
                if response.status_code not in RETRY_STATUSES or attempt == MAX_RETRIES:
                    raise ProviderError(
                        self.name,
                        f"HTTP {response.status_code} at {url}: {self.excerpt(response.text)}",
                        url=url,
                        status=response.status_code,
                    )
                await asyncio.sleep(retry_delay(response, attempt, self.backoff, self.cfg.timeout))
        raise ProviderError(self.name, f"cannot connect to any endpoint: {', '.join(tried)}")

    async def request(
        self, method: str, path: str, *, json: Any = None, params: Mapping[str, Any] | None = None, root: bool = False
    ) -> httpx.Response:
        response = await self.open(method, path, json=json, params=params, root=root)
        self.slots.release()
        return response

    def decode(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            raise ProviderError(
                self.name, f"invalid JSON at {response.request.url}", url=str(response.request.url)
            ) from None

    async def post_json(self, path: str, body: Mapping[str, Any], *, root: bool = False) -> Any:
        return self.decode(await self.request("POST", path, json=body, root=root))

    async def get_json(self, path: str, params: Mapping[str, Any] | None = None, *, root: bool = False) -> Any:
        return self.decode(await self.request("GET", path, params=params, root=root))

    async def stream_lines(self, path: str, body: Mapping[str, Any]) -> AsyncGenerator[str]:
        """The `data:` payload of each server-sent event. Retries apply only before the first byte."""
        response = await self.open("POST", path, json=body, stream=True)
        try:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    yield line.removeprefix("data:").strip()
        except httpx.HTTPError as error:
            url = str(response.request.url)
            raise ProviderError(self.name, f"{type(error).__name__} during stream at {url}", url=url) from None
        finally:
            try:
                await response.aclose()
            finally:
                self.slots.release()


async def unload(client: ProviderClient, release: str, model: str) -> None:
    """Free the model's memory: llama-swap unloads every model on its server; Ollama only `model`."""
    if release == "llama-swap":
        await client.request("GET", "/unload", root=True)
    elif release == "ollama":
        await client.post_json("/api/generate", {"model": model, "keep_alive": 0}, root=True)


async def unload_supported(client: ProviderClient, release: str) -> bool:
    paths = {"llama-swap": "/running", "ollama": "/api/version"}
    if release not in paths:
        return False
    try:
        await client.request("GET", paths[release], root=True)
    except ProviderError:
        return False
    return True


async def probe(client: ProviderClient, block: str, call: Callable[[], Awaitable[str | None]]) -> ProviderHealth:
    """Time one small request (`call` returns the model the endpoint reports) and check unload support."""
    cfg = client.cfg
    model: str | None = cfg.model or None
    status, error, latency = "ok", None, None
    start = perf_counter()
    try:
        model = await call() or model
        latency = round((perf_counter() - start) * 1000, 1)
    except ProviderError as failure:
        status, error = "failed", str(failure)
    unload = "n/a"
    if cfg.release != "none":
        unload = "yes" if await unload_supported(client, cfg.release) else "no"
    return ProviderHealth(
        block=block,
        provider=cfg.provider,
        base_url=cfg.base_url,
        device=cfg.device,
        status=status,
        model=model,
        latency_ms=latency,
        unload=unload,
        error=error,
    )

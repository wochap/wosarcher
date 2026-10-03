"""Provider HTTP client (timeouts, retries, fallback URLs, concurrency) and usage recording."""

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from wosarcher.config import Prices, Provider

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
        self.slots = asyncio.Semaphore(cfg.concurrency)

    def excerpt(self, text: str) -> str:
        key = self.cfg.api_key.get_secret_value() if self.cfg.api_key else ""
        short = text[:200]
        return short.replace(key, "***") if key else short

    async def post_json(self, path: str, body: Mapping[str, Any]) -> Any:
        headers = {"Authorization": f"Bearer {self.cfg.api_key.get_secret_value()}"} if self.cfg.api_key else {}
        timeout = httpx.Timeout(self.cfg.timeout, connect=self.cfg.connect_timeout)
        tried: list[str] = []
        for base in [self.cfg.base_url, *self.cfg.fallback_urls]:
            url = f"{base.rstrip('/')}/{path.lstrip('/')}"
            tried.append(url)
            for attempt in range(MAX_RETRIES + 1):
                try:
                    async with self.slots:
                        response = await self.http.post(url, json=body, headers=headers, timeout=timeout)
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    break
                except httpx.HTTPError as error:
                    raise ProviderError(self.name, f"{type(error).__name__} at {url}", url=url) from None
                if response.status_code < 400:
                    return response.json()
                if response.status_code not in RETRY_STATUSES or attempt == MAX_RETRIES:
                    raise ProviderError(
                        self.name,
                        f"HTTP {response.status_code} at {url}: {self.excerpt(response.text)}",
                        url=url,
                        status=response.status_code,
                    )
                await asyncio.sleep(retry_delay(response, attempt, self.backoff, self.cfg.timeout))
        raise ProviderError(self.name, f"cannot connect to any endpoint: {', '.join(tried)}")

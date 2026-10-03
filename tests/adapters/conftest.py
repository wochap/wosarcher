from collections.abc import AsyncIterator

import httpx
import pytest

from wosarcher.config import Provider
from wosarcher.http import ProviderClient, UsageLedger
from wosarcher.models import Chunk, chunk_id


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def ledger() -> UsageLedger:
    return UsageLedger({})


def provider_client(cfg: Provider, http: httpx.AsyncClient, ledger: UsageLedger) -> ProviderClient:
    return ProviderClient(cfg.provider, cfg, http, ledger, backoff=0)


def chunks(*texts: str) -> list[Chunk]:
    return [
        Chunk(chunk_id=chunk_id("s", i, text), source_id="s", position=i, text=text) for i, text in enumerate(texts)
    ]

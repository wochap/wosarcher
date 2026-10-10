"""Composition root: settings in, adapters out. The dicts below are data, not a registry."""

from collections.abc import Callable, Mapping

import httpx

from wosarcher.adapters.bm25 import Bm25Scorer
from wosarcher.adapters.command import CommandHook
from wosarcher.adapters.embeddings import OpenAIEmbedder
from wosarcher.adapters.firecrawl import FirecrawlFetcher
from wosarcher.adapters.jev import JevScorer
from wosarcher.adapters.llm import ChatLLM
from wosarcher.adapters.pandoc import PandocExporter
from wosarcher.adapters.passthrough import PassthroughScorer
from wosarcher.adapters.rerank import RerankScorer
from wosarcher.adapters.searxng import SearxngSearcher
from wosarcher.adapters.webhook import WebhookHook
from wosarcher.config import HookEntry, Provider, ScoreConfig, Settings
from wosarcher.http import ProviderClient, UsageLedger
from wosarcher.ports import Adapters, Embedder, Exporter, Hook, Managed, Scorer

ScorerFactory = Callable[[ScoreConfig, ProviderClient | None, UsageLedger], Scorer]


def remote_scorer(make: Callable[[ScoreConfig, ProviderClient, UsageLedger], Scorer]) -> ScorerFactory:
    def factory(cfg: ScoreConfig, client: ProviderClient | None, ledger: UsageLedger) -> Scorer:
        if client is None:
            raise ValueError(f"score.provider '{cfg.provider}' needs an endpoint")
        return make(cfg, client, ledger)

    return factory


SCORERS: dict[str, ScorerFactory] = {
    "rerank": remote_scorer(RerankScorer),
    "jev": remote_scorer(JevScorer),
    "bm25": lambda cfg, client, ledger: Bm25Scorer(),
    "passthrough": lambda cfg, client, ledger: PassthroughScorer(),
}
PREFILTERS: dict[str, Callable[[Provider, ProviderClient, UsageLedger], Embedder] | None] = {
    "embeddings": OpenAIEmbedder,
    "bm25": None,
    "none": None,
}
PROVIDERS = {
    "search": ["searxng"],
    "fetch": ["firecrawl"],
    "prefilter": list(PREFILTERS),
    "score": ["rerank", "jev", "bm25"],
    "llm": ["openai"],
}
REMOTE = {"searxng", "firecrawl", "embeddings", "rerank", "jev", "openai"}


def check_providers(settings: Settings) -> None:
    for block, allowed in PROVIDERS.items():
        provider = getattr(settings, block).provider
        if provider not in allowed:
            raise ValueError(f"{block}.provider '{provider}' is not one of: {', '.join(allowed)}")


def build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
    check_providers(settings)

    def client(cfg: Provider) -> ProviderClient:
        return ProviderClient(cfg.provider, cfg, http, ledger)

    managed: dict[str, Managed] = {}
    searcher = SearxngSearcher(settings.search, client(settings.search), ledger)
    fetcher = FirecrawlFetcher(settings.fetch, client(settings.fetch), ledger)
    managed.update(search=searcher, fetch=fetcher)

    embedder: Embedder | None = None
    make_embedder = PREFILTERS[settings.prefilter.provider]
    if make_embedder is not None:
        embedder = make_embedder(settings.prefilter, client(settings.prefilter), ledger)
        if isinstance(embedder, OpenAIEmbedder):
            managed["prefilter"] = embedder

    score = settings.score
    score_client = client(score) if score.provider in REMOTE else None
    scorers = {name: SCORERS[name](score, score_client, ledger) for name in [score.provider, *score.fallback]}
    remote = scorers[score.provider]
    if isinstance(remote, RerankScorer | JevScorer):
        managed["score"] = remote

    llm_client = client(settings.llm)
    planner = ChatLLM(settings.llm, llm_client, ledger, "plan")
    gapper = ChatLLM(settings.llm, llm_client, ledger, "gap")
    writer = ChatLLM(settings.llm, llm_client, ledger, "write")
    managed["llm"] = planner
    return Adapters(
        searcher=searcher,
        fetcher=fetcher,
        embedder=embedder,
        scorers=scorers,
        planner=planner,
        gapper=gapper,
        writer=writer,
        managed=managed,
    )


def exporter() -> Exporter:
    """Report export; it needs no profile settings, so runs do not build it."""
    return PandocExporter()


HOOKS: dict[str, Callable[[HookEntry, Mapping[str, str]], Hook]] = {
    "webhook": lambda entry, env: WebhookHook(entry),
    "command": CommandHook,
}


def hooks(entries: list[HookEntry], env: Mapping[str, str]) -> list[tuple[HookEntry, Hook]]:
    """A hook per resolved entry (`config.resolve_hook`); `env` is the server's environment."""
    return [(entry, HOOKS[entry.kind](entry, env)) for entry in entries]

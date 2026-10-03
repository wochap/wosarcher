"""Port wrappers over the store caches: a caching Fetcher and the prefilter's embedding mapping."""

from collections.abc import Iterator, MutableMapping

from wosarcher.models import Page, normalise_url
from wosarcher.ports import Fetcher
from wosarcher.store.caches import EmbeddingCache, PageCache


class CachedFetcher:
    """A Fetcher that answers from the page cache when it can; `cached` holds the normalised URLs it answered."""

    def __init__(self, fetcher: Fetcher, cache: PageCache) -> None:
        self.fetcher = fetcher
        self.cache = cache
        self.cached: set[str] = set()

    async def fetch(self, url: str) -> Page:
        page = self.cache.get(url)
        if page is not None:
            self.cached.add(normalise_url(url))
            return page
        page = await self.fetcher.fetch(url)
        if page.text.strip():
            self.cache.put(page, url)
        return page


class EmbeddingMapping(MutableMapping[str, list[float]]):
    """Vectors of one (model, dimension), keyed by the text's SHA-256 hex, stored in the embedding cache."""

    def __init__(self, cache: EmbeddingCache, model: str, dim: int) -> None:
        self.cache = cache
        self.model = model
        self.dim = dim

    def __getitem__(self, key: str) -> list[float]:
        vector = self.cache.get(self.model, self.dim, key)
        if vector is None:
            raise KeyError(key)
        return vector

    def __setitem__(self, key: str, vector: list[float]) -> None:
        self.cache.put(self.model, self.dim, key, vector)

    def __delitem__(self, key: str) -> None:
        path = self.cache.path(self.model, self.dim, key)
        if not path.is_file():
            raise KeyError(key)
        path.unlink()

    def __iter__(self) -> Iterator[str]:
        return iter(self.cache.keys(self.model, self.dim))

    def __len__(self) -> int:
        return sum(1 for _ in self)

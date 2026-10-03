"""Caches shared by runs: fetched pages by normalised URL, embeddings by text, model, and dimension."""

import json
import re
import time
from array import array
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from wosarcher.models import Page, normalise_url


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


class PageCache:
    """`<dir>/<sha256(normalised url)>.json` holding the page and when it was fetched. TTL 0 disables it."""

    def __init__(self, directory: Path, ttl_hours: float, clock: Callable[[], float] = time.time) -> None:
        self.directory = directory
        self.ttl = ttl_hours * 3600
        self.clock = clock

    def path(self, url: str) -> Path:
        return self.directory / f"{sha256(normalise_url(url).encode('utf-8')).hexdigest()}.json"

    def get(self, url: str) -> Page | None:
        path = self.path(url)
        if self.ttl <= 0 or not path.is_file():
            return None
        entry = json.loads(path.read_text(encoding="utf-8"))
        if self.clock() - float(entry["fetched_at"]) >= self.ttl:
            return None
        return Page.model_validate(entry["page"])

    def put(self, page: Page, url: str | None = None) -> None:
        if self.ttl <= 0:
            return
        entry = {"fetched_at": self.clock(), "page": page.model_dump(mode="json")}
        write_atomic(self.path(url or page.source.uri), json.dumps(entry).encode("utf-8"))


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model) or "_"


class EmbeddingCache:
    """`<dir>/<model>/<dim>/<key[:2]>/<key>.f32`: raw little-endian float32; `key` is the text's SHA-256 hex."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path(self, model: str, dim: int, key: str) -> Path:
        return self.directory / slug(model) / str(dim) / key[:2] / f"{key}.f32"

    def keys(self, model: str, dim: int) -> list[str]:
        return [path.stem for path in sorted((self.directory / slug(model) / str(dim)).glob("*/*.f32"))]

    def get(self, model: str, dim: int, key: str) -> list[float] | None:
        path = self.path(model, dim, key)
        if not path.is_file():
            return None
        vector = array("f")
        vector.frombytes(path.read_bytes())
        if len(vector) != dim:
            return None
        return vector.tolist()

    def put(self, model: str, dim: int, key: str, vector: list[float]) -> None:
        if len(vector) != dim:
            return
        write_atomic(self.path(model, dim, key), array("f", vector).tobytes())

"""Data contracts that flow between stages, and their stable identities."""

from hashlib import sha256
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

TRACKING_PARAMETERS = {"fbclid", "gclid"}


class Contract(BaseModel):
    """Base for contracts: immutable, and unknown fields are errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def normalise_url(url: str) -> str:
    """Lowercase scheme and host, drop fragment, trailing slash, and tracking parameters; sort the query."""
    parts = urlsplit(url.strip())
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def short_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()[:16]


def web_source_id(url: str) -> str:
    return short_hash("web\n" + normalise_url(url))


def file_source_id(content: bytes) -> str:
    return short_hash("file\n" + sha256(content).hexdigest())


def chunk_id(source_id: str, position: int, text: str) -> str:
    return short_hash(f"{source_id}\n{position}\n{text}")


class WritingOptions(Contract):
    tone: str = "objective"
    tone_instructions: str = ""
    words: int = Field(default=1200, gt=0)
    language: str = "english"
    citation_marker: Literal["numeric", "superscript", "author-year"] = "numeric"
    reference_style: str = "APA"


class Query(Contract):
    query_id: str
    text: str


class Hit(Contract):
    url: str
    title: str
    snippet: str = ""
    rank: int = Field(default=1, ge=1)
    query_ids: tuple[str, ...] = ()


class Source(Contract):
    source_id: str
    kind: Literal["web", "file"]
    uri: str
    title: str


class Page(Contract):
    source: Source
    markdown: str


class Chunk(Contract):
    chunk_id: str
    source_id: str
    position: int = Field(ge=0)
    text: str
    heading_path: tuple[str, ...] = ()


class Score(Contract):
    query_id: str
    chunk_id: str
    value: float
    scorer: str


class Passage(Contract):
    """One selected chunk; `n` is its citation number."""

    n: int = Field(gt=0)
    chunk_id: str
    source_id: str
    query_id: str
    text: str
    heading_path: tuple[str, ...] = ()
    score: float


class Context(Contract):
    passages: tuple[Passage, ...] = ()
    sources: tuple[Source, ...] = ()
    scorer: str = ""


class Report(Contract):
    markdown: str
    sources: tuple[Source, ...] = ()


Stage = Literal["plan", "search", "fetch", "load", "chunk", "prefilter", "score", "select", "write"]


class RunRequest(Contract):
    query: str = Field(min_length=1)
    sources: Literal["files", "web", "both"] = "both"
    attachments: tuple[str, ...] = ()
    until: Stage | None = None
    profile: str | None = None
    overrides: tuple[str, ...] = ()
    writing: WritingOptions = WritingOptions()


class Message(Contract):
    role: Literal["system", "user", "assistant"]
    content: str


class Completion(Contract):
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class EmbedderInfo(Contract):
    """The embedding model identity used in cache keys."""

    model: str
    dimension: int = Field(gt=0)


class ProviderHealth(Contract):
    """One row of `wosarcher doctor`: a configured block and its probe result."""

    block: str
    provider: str
    base_url: str = ""
    device: str | None = None
    status: Literal["ok", "failed", "built-in"]
    model: str | None = None
    latency_ms: float | None = None
    unload: Literal["yes", "no", "n/a"] = "n/a"
    error: str | None = None


class DoctorReport(Contract):
    providers: tuple[ProviderHealth, ...] = ()
    warnings: tuple[str, ...] = ()


CONTRACTS: tuple[type[Contract], ...] = (
    RunRequest,
    Query,
    Hit,
    Source,
    Page,
    Chunk,
    Score,
    Passage,
    Context,
    Report,
    WritingOptions,
    Message,
    Completion,
    EmbedderInfo,
    ProviderHealth,
    DoctorReport,
)

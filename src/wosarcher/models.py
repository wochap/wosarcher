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


Sources = Literal["both", "web", "files"]


class Query(Contract):
    """`q0` is the main query; `q1`, `q2`, ... are sub-queries."""

    id: str
    text: str


class Plan(Contract):
    queries: list[Query]
    """`queries[0]` is the main query."""
    warnings: list[str] = []


class Hit(Contract):
    url: str
    title: str
    snippet: str
    rank: int = Field(ge=1)
    """Best (lowest) rank over the queries that found it, 1-based."""
    query_ids: list[str]


class Source(Contract):
    source_id: str
    kind: Literal["web", "file"]
    uri: str
    """Normalised URL, or the attachment name."""
    title: str
    author: str | None = None
    published: str | None = None


class Page(Contract):
    source: Source
    text: str
    format: Literal["markdown", "pdf-ingest"] = "markdown"
    truncated: bool = False
    """Set by the Fetcher when it cut the text at `fetch.max_chars`."""
    rank: int = 0
    """Hit rank; 0 for files."""
    query_ids: list[str] = []
    """Empty for files."""


class Chunk(Contract):
    chunk_id: str
    source_id: str
    position: int = Field(ge=0)
    text: str
    heading_path: list[str] = []
    page_id: str | None = None
    block_ids: list[str] = []


class Attachment(Contract):
    """Attachment bytes read by `attachments.collect` or received by the server."""

    name: str
    data: bytes


class Skipped(Contract):
    """An item that did not make it: a failed search or fetch, or a skipped file."""

    item: str
    reason: str


class SearchResult(Contract):
    hits: list[Hit]
    failures: list[Skipped] = []


class FetchResult(Contract):
    pages: list[Page]
    failures: list[Skipped] = []


class LoadResult(Contract):
    pages: list[Page]
    skipped: list[Skipped] = []


class ChunkResult(Contract):
    chunks: list[Chunk]
    duplicates: int = 0


class Score(Contract):
    query_id: str
    chunk_id: str
    value: float
    scorer: str
    display: float | None = None
    """0 to 1 for the UI; None for passthrough."""
    kept: bool = False


class Candidate(Contract):
    """A chunk and query pair that reaches the score stage."""

    query_id: str
    chunk_id: str
    prefilter: float | None = None
    """Similarity or BM25 value; None when not ranked."""
    passthrough: bool = False
    """Small-input passthrough: scored by `passthrough` whatever the scorer."""


class PrefilterResult(Contract):
    candidates: list[Candidate]
    method: Literal["embeddings", "bm25", "none"]
    """The method that actually ran."""
    warnings: list[str] = []


class QueryScores(Contract):
    """One query's scoring report."""

    query_id: str
    scorer: str
    scored: int
    kept: int
    threshold_display: float | None
    passages: list[Score]
    """Kept pairs, best first."""


class ScoreResult(Contract):
    scores: list[Score]
    """Every pair, kept or not."""
    scorer: str
    """The chain entry that ran."""
    failed: list[Skipped] = []
    """`item` is the scorer name, `reason` the error."""
    queries: list[QueryScores]


class Passage(Contract):
    """One selected chunk; `n` is its citation number."""

    n: int = Field(gt=0)
    chunk_id: str
    source_id: str
    query_id: str
    """The chunk's best query ID."""
    text: str
    heading_path: list[str] = []
    page_id: str | None = None
    block_ids: list[str] = []
    scorer: str
    display: float | None = None


class Context(Contract):
    query: str
    passages: list[Passage]
    """Ordered by `n`."""
    sources: list[Source]
    """The source of each passage, once, in first-use order."""
    budget_tokens: int
    used_tokens: int


class Report(Contract):
    markdown: str
    sources: tuple[Source, ...] = ()


Stage = Literal["plan", "search", "fetch", "load", "chunk", "prefilter", "score", "select", "write"]


class RunRequest(Contract):
    query: str = Field(min_length=1)
    sources: Sources = "both"
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
    Plan,
    Hit,
    Source,
    Page,
    Chunk,
    Attachment,
    Skipped,
    SearchResult,
    FetchResult,
    LoadResult,
    ChunkResult,
    Score,
    Candidate,
    PrefilterResult,
    QueryScores,
    ScoreResult,
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

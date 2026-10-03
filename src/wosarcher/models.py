"""Data contracts that flow between stages, and their stable identities."""

from datetime import datetime
from hashlib import sha256
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    model_serializer,
)

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


class Reference(Contract):
    source_id: str
    entry: str
    """Formatted in the reference style."""
    passages: list[int]
    """Cited passage numbers from this source, ascending."""


class Report(Contract):
    body: str
    """LLM text with `[n]` markers, as streamed."""
    markdown: str
    """Rendered markers plus `## References`."""
    cited: list[int]
    """Known cited numbers, in order of first citation."""
    references: list[Reference]
    warnings: list[str] = []


Stage = Literal["load", "plan", "search", "fetch", "chunk", "prefilter", "score", "select", "write"]
STAGES: tuple[Stage, ...] = ("load", "plan", "search", "fetch", "chunk", "prefilter", "score", "select", "write")
"""Run order."""


class RunRequest(Contract):
    query: str = Field(min_length=1)
    sources: Sources = "both"
    until: Stage | None = None
    """None runs to the report; `select` stops at the context."""
    attachments: list[str] = []
    """Paths under the run's `attachments/`, as copied."""


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


# Runs


class RunRecord(Contract):
    """`request.json`: what a run was asked, with which configuration, and where it came from."""

    run_id: str
    created_at: datetime
    request: RunRequest
    profile: str
    overrides: list[str] = []
    """Every `--set` value, the parent's first."""
    changes: list[str] = []
    """The overrides this fork added."""
    settings: dict[str, Any]
    """Resolved configuration, secrets as `***`."""
    parent_run_id: str | None = None
    fork_from: Stage | None = None
    version: int = Field(default=1, ge=1)


RunStatus = Literal["queued", "running", "done", "failed", "cancelled", "interrupted"]
"""`queued` and `running` come from the server; a run with no terminal event and no process is `interrupted`."""


class RunSummary(Contract):
    """One run as `wosarcher runs --json` and `GET /api/runs` list it."""

    run_id: str
    query: str
    status: RunStatus
    created: datetime
    parent_run_id: str | None = None
    version: int = 1
    fork_from: Stage | None = None
    profile: str
    sources: Sources = "both"
    until: Stage | None = None
    writing: WritingOptions = WritingOptions()
    """The run's resolved writing options."""
    duration_s: float | None = None
    """`run.started` to the terminal run event; None while queued or running, and for interrupted runs."""
    cost: float | None = None
    """Dollars from `costs.json`; None when it is missing."""
    queue_position: int | None = None
    """1 for the next run to start; None unless queued."""


class RunOutput(Contract):
    """What `wosarcher run --json` and `wosarcher fork --json` print."""

    run_id: str
    status: Literal["done", "failed", "cancelled"]
    error: str | None = None
    run_dir: str
    context: Context | None = None
    report: Report | None = None


class UsageTotals(Contract):
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    units: float = 0
    cost: float = 0
    """Dollars; 0 when no price is configured."""


class RunCosts(Contract):
    """`costs.json`."""

    stages: dict[str, UsageTotals]
    providers: dict[str, UsageTotals]
    total: UsageTotals


# Server API: request and response bodies of `/api`.


class WritingPatch(Contract):
    """Any subset of the writing options; unset fields keep the value from the layer below."""

    tone: str | None = None
    tone_instructions: str | None = None
    words: int | None = Field(default=None, gt=0)
    language: str | None = None
    citation_marker: Literal["numeric", "superscript", "author-year"] | None = None
    reference_style: str | None = None


class RunCreate(Contract):
    """The `request` field of `POST /api/runs`."""

    query: str = Field(min_length=1)
    sources: Sources | None = None
    """None: the global default."""
    until: Stage | None = None
    profile: str | None = None
    writing: WritingPatch = WritingPatch()
    set: list[str] = []
    """`dotted.key=value` overrides, applied last."""


class ForkCreate(Contract):
    """The body of `POST /api/runs/{id}/fork`."""

    model_config = ConfigDict(frozen=True, extra="forbid", serialize_by_alias=True)

    from_stage: Stage = Field(validation_alias=AliasChoices("from", "from_stage"), serialization_alias="from")
    writing: WritingPatch = WritingPatch()
    set: list[str] = []
    profile: str | None = None


class RunCreated(Contract):
    run_id: str
    status: Literal["queued", "running"]


class RunDetail(RunSummary):
    """`GET /api/runs/{id}`: the summary plus the stored record, costs, and the last logged `seq`."""

    request: RunRecord | None = None
    """None while queued."""
    costs: RunCosts | None = None
    last_seq: int = 0


class ServerSettings(Contract):
    """Global defaults for runs started by the server (`server-settings.json`)."""

    writing: WritingOptions = WritingOptions()
    sources: Sources = "both"


class ProfileInfo(Contract):
    name: str
    source: Literal["builtin", "user"]
    active: bool


class ProviderCheck(Contract):
    role: str
    provider: str
    url: str = ""
    model: str | None = None
    device: str | None = None
    status: Literal["ok", "degraded", "down", "skipped"]
    latency_ms: float | None = None
    detail: str = ""


class HealthReport(Contract):
    profile: str
    checks: list[ProviderCheck]
    warnings: list[str] = []


class ApiError(Contract):
    error: str
    detail: str


# Events: `data` field names are contracts the server and the frontend read.


class RunQueuedData(Contract):
    position: int


class RunStartedData(Contract):
    query: str
    profile: str
    parent_run_id: str | None
    version: int
    until: Stage | None


class RunDoneData(Contract):
    until: Stage | None
    totals: UsageTotals


class RunFailedData(Contract):
    stage: Stage | None
    error: str


class RunCancelledData(Contract):
    stage: Stage | None


class StageStartedData(Contract):
    device: str | None
    provider: str


class StageProgressData(Contract):
    done: int
    total: int
    failed: int


class StageDoneData(Contract):
    count: int
    seconds: float
    usage: UsageTotals = UsageTotals()
    provider: str | None = None
    skipped: bool = False
    copied_from: str | None = None
    warnings: list[str] = []


class StageFailedData(Contract):
    error: str
    next: str
    """The fallback that ran next; empty when none."""


class ResourceData(Contract):
    device: str
    released_stage: Stage


class PlanReadyData(Contract):
    queries: list[Query]


class HitFoundData(Contract):
    url: str
    title: str
    query_ids: list[str]


class PageFetchedData(Contract):
    url: str
    source_id: str
    title: str
    chars: int
    cached: bool


class PageFailedData(Contract):
    url: str
    reason: str


class KeptPassage(Contract):
    chunk_id: str
    source_id: str
    title: str
    uri: str
    heading_path: list[str] = []
    text: str
    display: float | None


class PassagesScoredData(Contract):
    query_id: str
    scorer: str
    scored: int
    kept: int
    threshold_display: float | None
    passages: list[KeptPassage]


class ReportTextData(Contract):
    text: str


class EventBase(Contract):
    seq: int = Field(ge=0)
    run_id: str
    ts: datetime
    stage: Stage | None = None
    """Absent when the event is not about a stage."""

    @model_serializer(mode="wrap")
    def drop_empty_stage(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        out: dict[str, Any] = handler(self)
        if out.get("stage") is None:
            out.pop("stage", None)
        return out


class RunQueued(EventBase):
    type: Literal["run.queued"] = "run.queued"
    data: RunQueuedData


class RunStarted(EventBase):
    type: Literal["run.started"] = "run.started"
    data: RunStartedData


class RunDone(EventBase):
    type: Literal["run.done"] = "run.done"
    data: RunDoneData


class RunFailed(EventBase):
    type: Literal["run.failed"] = "run.failed"
    data: RunFailedData


class RunCancelled(EventBase):
    type: Literal["run.cancelled"] = "run.cancelled"
    data: RunCancelledData


class StageStarted(EventBase):
    type: Literal["stage.started"] = "stage.started"
    data: StageStartedData


class StageProgress(EventBase):
    type: Literal["stage.progress"] = "stage.progress"
    data: StageProgressData


class StageDone(EventBase):
    type: Literal["stage.done"] = "stage.done"
    data: StageDoneData


class StageFailed(EventBase):
    type: Literal["stage.failed"] = "stage.failed"
    data: StageFailedData


class ResourceWaiting(EventBase):
    type: Literal["resource.waiting"] = "resource.waiting"
    data: ResourceData


class ResourceReleased(EventBase):
    type: Literal["resource.released"] = "resource.released"
    data: ResourceData


class PlanReady(EventBase):
    type: Literal["plan.ready"] = "plan.ready"
    data: PlanReadyData


class HitFound(EventBase):
    type: Literal["hit.found"] = "hit.found"
    data: HitFoundData


class PageFetched(EventBase):
    type: Literal["page.fetched"] = "page.fetched"
    data: PageFetchedData


class PageFailed(EventBase):
    type: Literal["page.failed"] = "page.failed"
    data: PageFailedData


class PassagesScored(EventBase):
    type: Literal["passages.scored"] = "passages.scored"
    data: PassagesScoredData


class ReportDelta(EventBase):
    type: Literal["report.delta"] = "report.delta"
    data: ReportTextData


class ReportSnapshot(EventBase):
    type: Literal["report.snapshot"] = "report.snapshot"
    data: ReportTextData


EVENT_TYPES: tuple[type[EventBase], ...] = (
    RunQueued,
    RunStarted,
    RunDone,
    RunFailed,
    RunCancelled,
    StageStarted,
    StageProgress,
    StageDone,
    StageFailed,
    ResourceWaiting,
    ResourceReleased,
    PlanReady,
    HitFound,
    PageFetched,
    PageFailed,
    PassagesScored,
    ReportDelta,
    ReportSnapshot,
)

Event = Annotated[
    RunQueued
    | RunStarted
    | RunDone
    | RunFailed
    | RunCancelled
    | StageStarted
    | StageProgress
    | StageDone
    | StageFailed
    | ResourceWaiting
    | ResourceReleased
    | PlanReady
    | HitFound
    | PageFetched
    | PageFailed
    | PassagesScored
    | ReportDelta
    | ReportSnapshot,
    Field(discriminator="type"),
]
EVENT: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(line: str) -> Event:
    return EVENT.validate_json(line)


def make_event(seq: int, run_id: str, ts: datetime, event_type: str, stage: Stage | None, data: BaseModel) -> Event:
    """Build the event named by `event_type`; `data` must be its data model."""
    return EVENT.validate_python(
        {"seq": seq, "run_id": run_id, "ts": ts, "type": event_type, "stage": stage, "data": data}
    )


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
    Reference,
    Report,
    WritingOptions,
    Message,
    Completion,
    EmbedderInfo,
    ProviderHealth,
    DoctorReport,
    RunRecord,
    RunSummary,
    RunOutput,
    RunCosts,
    WritingPatch,
    RunCreate,
    ForkCreate,
    RunCreated,
    RunDetail,
    ServerSettings,
    ProfileInfo,
    ProviderCheck,
    HealthReport,
    ApiError,
    *EVENT_TYPES,
)

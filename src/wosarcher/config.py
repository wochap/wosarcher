"""Run configuration: settings models, provider entries, profiles, precedence, and secret redaction.

`resolve()` is the whole story: pick a profile and one provider entry per
block, then merge built-in defaults < entries < the chosen model's values (entry, then
profile `models`) < profile < `WOSARCHER_*` environment < depth preset < `--set` overrides, and
validate once.
"""

import json
import re
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple, cast, get_args
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import to_jsonable_python

from wosarcher.models import (
    Effort,
    ExpandMode,
    FinishedStatus,
    Limits,
    Stage,
    Structure,
    WritingOptions,
    domain_list,
    search_language,
)

ENV_PREFIX = "WOSARCHER_"
CLIENT_ENV = ("WOSARCHER_URL", "WOSARCHER_TOKEN", "WOSARCHER_SOCKET", "WOSARCHER_DEPTH")
"""The `wosarcher` client's variables; not settings."""
BUILTIN_DEPTHS = Path(__file__).parent / "depths"
DEPTH_ORDER = ("quick", "standard", "deep", "exhaustive")
CUSTOM_DEPTH = "custom"
BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
BLOCKS = ("search", "fetch", "prefilter", "score", "llm")
"""The provider blocks, each filled by one entry of `providers/<block>/`."""

# Typed research fields (CLI flags, `RunCreate.research`) and the key each sets.
RESEARCH_KEYS = {
    "sub_queries": "plan.max_sub_queries",
    "results_per_query": "search.max_results",
    "max_pages": "fetch.max_pages",
    "passages_per_query": "score.top_k",
    "rounds": "research.rounds",
    "queries_per_round": "research.queries_per_round",
}
# Typed LLM fields (`RunCreate.llm`, CLI flags) besides `model` and `reasoning`, and the key each sets.
LLM_KEYS = {
    "context_window": "llm.context_window",
    "max_output_tokens": "llm.max_output_tokens",
    "context_tokens": "select.max_context_tokens",
    "gap_context_tokens": "research.gap_context_tokens",
}
# The only keys a depth preset may set, besides its `description`; no entry or profile sets them.
DEPTH_KEYS = (*RESEARCH_KEYS.values(), "write.words")
# What a model of an llm entry's `models` table may set, and the key each fills.
MODEL_FIELDS = {
    "context_window": "llm.context_window",
    "max_output_tokens": "llm.max_output_tokens",
    "reasoning": "llm.reasoning",
    "gap_context_tokens": "research.gap_context_tokens",
}
# Keys inside the provider blocks that the profile owns, not the entry.
PROFILE_BLOCK_KEYS = (
    "llm.model",
    "search.allow_domains",
    "search.block_domains",
    "search.language",
    "search.time_range",
    "search.filter_pages",
)

# Seconds each stage may take; `run.stage_timeouts` overrides single stages.
DEFAULT_STAGE_TIMEOUTS: dict[Stage, float] = {
    "load": 60,
    "plan": 180,
    "search": 120,
    "fetch": 600,
    "chunk": 60,
    "prefilter": 600,
    "score": 900,
    "gap": 360,
    "select": 60,
    "write": 1800,
    "draft": 360,
    "expand": 60,
    "extract": 1800,
    "assemble": 60,
}

# Concurrency per adapter when a block leaves `concurrency` unset.
DEFAULT_CONCURRENCY = {"searxng": 4, "firecrawl": 6, "embeddings": 4, "rerank": 4, "jev": 64, "openai": 1}


class ConfigError(Exception):
    pass


class Block(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def check_one_source(block: BaseModel, name: str) -> None:
    """At most one of `<name>`, `<name>_file`, and `<name>_command` may be set."""
    forms = (name, f"{name}_file", f"{name}_command")
    if sum(getattr(block, form) is not None for form in forms) > 1:
        raise ValueError(f"{name}: set only one of {', '.join(forms)}")


class Prices(Block):
    input_per_mtok: float | None = None
    output_per_mtok: float | None = None
    per_unit: float | None = None


class Provider(Block):
    """The shape every provider block shares."""

    provider: str
    base_url: str = ""
    api_key: SecretStr | None = None
    api_key_file: str | None = None
    api_key_command: list[str] | None = None
    model: str = ""
    device: str | None = None
    release: Literal["none", "llama-swap", "ollama"] = "none"
    fallback_urls: list[str] = []
    batch_size: int = Field(default=16, gt=0)
    concurrency: int | None = Field(default=None, gt=0)
    connect_timeout: float = Field(default=3.0, gt=0)
    timeout: float = Field(default=60.0, gt=0)
    retry_budget: float = Field(default=60.0, ge=0)
    prices: Prices = Prices()

    @model_validator(mode="after")
    def check_api_key(self) -> "Provider":
        check_one_source(self, "api_key")
        return self


class SearchConfig(Provider):
    max_results: int = Field(default=10, ge=1)
    language: str = ""
    time_range: Literal["", "day", "week", "month", "year"] = ""
    allow_domains: list[str] = []
    """Empty allows every domain."""
    block_domains: list[str] = []
    filter_pages: int = Field(default=3, ge=1)
    """Result pages a query may read while a domain list is set."""

    @field_validator("allow_domains", "block_domains")
    @classmethod
    def check_domains(cls, value: list[str]) -> list[str]:
        return domain_list(value)

    @field_validator("language")
    @classmethod
    def check_language(cls, value: str) -> str:
        return search_language(value)


class FetchConfig(Provider):
    max_chars: int = Field(default=50000, ge=1)
    max_pages: int = Field(default=40, gt=0)
    only_main_content: bool = True
    page_timeout: float = Field(default=45.0, gt=0)


class ScoreConfig(Provider):
    min_score: float = 2.0
    relative_threshold: float = Field(default=0.5, ge=0, le=1)
    top_k: int = Field(default=10, gt=0)
    fallback: list[Literal["bm25", "passthrough"]] = ["bm25", "passthrough"]
    rerank_scale: Literal["auto", "probability", "logit"] = "auto"
    candidates: int = Field(default=50, gt=0)
    """Pairs per query the prefilter passes to this scorer."""


class PrefilterConfig(Provider):
    provider: str = "bm25"
    context: Literal["header", "body"] = "header"


class ReasoningConfig(Block):
    """Thinking effort per LLM step; see `models.Effort`."""

    plan: Effort = "none"
    gap: Effort = "none"
    write: Effort = "none"
    draft: Effort = "none"
    extract: Effort = "none"


class LLMConfig(Provider):
    provider: str = "openai"
    context_window: int = Field(default=32768, gt=0)
    chars_per_token: float = Field(default=3.5, gt=0)
    token_margin: float = Field(default=1.1, ge=1)
    max_tokens_field: Literal["max_completion_tokens", "max_tokens"] = "max_completion_tokens"
    reasoning: ReasoningConfig = ReasoningConfig()
    max_continuations: int = Field(default=2, ge=0)
    max_output_tokens: int = Field(default=8192, gt=0)
    """Caps the writer's output limit; a quarter of the default window."""
    timeout: float = Field(default=300.0, gt=0)
    """A small local model may take minutes on a long prompt before its first token."""

    @field_validator("provider")
    @classmethod
    def check_provider(cls, value: str) -> str:
        if value != "openai":
            raise ValueError(f"'{value}' is not a known LLM provider; use 'openai'")
        return value


class PlanConfig(Block):
    max_sub_queries: int = Field(default=3, ge=0)


class AttachConfig(Block):
    max_bytes: int = Field(default=5_000_000, gt=0)


class ChunkConfig(Block):
    size_chars: int = Field(default=1800, gt=0)
    overlap: int = Field(default=150, ge=0)
    min_chars: int = Field(default=500, ge=0)
    """Floor for merging short sections and for the last window; 0 turns both off."""

    @model_validator(mode="after")
    def check_sizes(self) -> "ChunkConfig":
        for name in ("overlap", "min_chars"):
            value = getattr(self, name)
            if value >= self.size_chars:
                raise ValueError(f"chunk.{name} ({value}) must be below chunk.size_chars ({self.size_chars})")
        return self


class SelectConfig(Block):
    passthrough_chars: int = Field(default=8000, ge=0)
    max_chunks_per_source: int = Field(default=5, gt=0)
    max_context_tokens: Annotated[int, Field(gt=0)] | Literal["auto"] = "auto"
    """`auto`: all the room the context window leaves."""
    file_share: float = Field(default=0.5, ge=0, le=1)
    prompt_reserve_tokens: int = Field(default=2000, ge=0)


class ResearchConfig(Block):
    rounds: int = Field(default=1, ge=1, le=8)
    """Research rounds; above 1, search through gap repeat."""
    queries_per_round: int = Field(default=3, gt=0)
    """Most follow-up queries the gap step keeps per round."""
    gap_context_tokens: Annotated[int, Field(gt=0)] | Literal["auto"] = 4000
    """Passage budget of the gap step's prompt; `auto`: all the room the context window leaves."""
    gap_parts: StrictBool = True
    """Send the plan's question parts to the gap step; a temporary switch for measuring that input."""


class CatalogConfig(Block):
    """Catalog runs: the defaults a structure's limits and expand mode take, and the extract stage's knobs."""

    max_depth: int = Field(default=3, ge=1, le=10)
    max_nodes: int = Field(default=200, ge=1, le=5000)
    pages_per_node: int = Field(default=2, ge=1, le=10)
    expand: ExpandMode = "both"
    max_children: int = Field(default=50, gt=0)
    """Children kept per extraction."""
    concurrency: int = Field(default=4, gt=0)
    """Extraction calls in flight."""
    context_tokens: Annotated[int, Field(gt=0)] | Literal["auto"] = "auto"
    """The extract budget; `auto`: all the room the context window leaves."""
    language: str = ""
    """Applied over a derived structure's `language` when set (`--search-language` without a structure)."""
    record_language: str = ""
    """Applied over a derived structure's `record_language` when set."""

    @property
    def limits(self) -> Limits:
        return Limits(max_depth=self.max_depth, max_nodes=self.max_nodes, pages_per_node=self.pages_per_node)


def catalog_structure(structure: Structure | dict[str, Any], catalog: CatalogConfig) -> Structure:
    """The structure with the `catalog` block's limits and expand mode filling the keys it leaves unset.

    Keys the structure sets win over the block; a `Structure` value counts every key as set that it was
    built with (`model_fields_set`).
    """
    data = structure.model_dump(exclude_unset=True) if isinstance(structure, Structure) else dict(structure)
    raw: object = data.get("limits") or {}
    limits = raw.model_dump(exclude_unset=True) if isinstance(raw, Limits) else cast(dict[str, Any], raw)
    data["limits"] = {**catalog.limits.model_dump(), **limits}
    data.setdefault("expand", catalog.expand)
    return Structure.model_validate(data)


class QuestionsConfig(Block):
    """Run questions: the pauses a run may make and how long each waits."""

    clarify: StrictBool = True
    """Ask about the brief after the plan (or the draft) and before any search."""
    rounds: StrictBool = True
    """Ask between research rounds and catalog waves."""
    timeout: int = Field(default=60, ge=0, le=3600)
    """Seconds without a user present before a pause continues with the recommended answers; 0 does not wait."""
    max_wait: int = Field(default=1800, ge=60, le=86400)
    """Seconds after which a pause continues whether or not a user is present."""


class RunConfig(Block):
    gpu_policy: Literal["shared", "exclusive"] = "shared"
    runs_dir: Path | None = None
    """None: `$XDG_DATA_HOME/wosarcher/runs`."""
    cache_dir: Path | None = None
    """None: `$XDG_CACHE_HOME/wosarcher`."""
    page_cache_ttl_hours: float = Field(default=24, ge=0)
    """0 disables the page cache."""
    stage_timeouts: dict[Stage, float] = DEFAULT_STAGE_TIMEOUTS
    preflight: Literal["off", "cloud", "all"] = "off"
    """Probe the run's providers before the first stage: none, cloud blocks only, or every block."""

    @field_validator("stage_timeouts", mode="before")
    @classmethod
    def fill_timeouts(cls, value: object) -> object:
        if isinstance(value, Mapping):
            return {**DEFAULT_STAGE_TIMEOUTS, **cast(Mapping[str, object], value)}
        return value


class ServerConfig(Block):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, gt=0, lt=65536)
    static_dir: Path = Path("web/dist")
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    forwarded_allow_ips: list[str] = ["127.0.0.1"]
    """Peers whose `X-Forwarded-For` and `X-Forwarded-Proto` are trusted: addresses, networks, or `*`."""
    socket: Path | None = None
    """The Unix socket `wosarcherd serve` listens on; None: `$XDG_RUNTIME_DIR/wosarcher.sock`, or none without it."""


class AuthConfig(Block):
    password_hash: SecretStr | None = None
    """None: the hash in `auth.json`, or no password at all."""
    password_hash_file: str | None = None
    password_hash_command: list[str] | None = None
    session_days: int = Field(default=30, gt=0)
    allowed_origins: list[str] = []
    """Origins besides the server's own that may send state-changing requests."""

    @model_validator(mode="after")
    def check_password_hash(self) -> "AuthConfig":
        check_one_source(self, "password_hash")
        return self


class Settings(Block):
    search: SearchConfig = SearchConfig(provider="searxng")
    fetch: FetchConfig = FetchConfig(provider="firecrawl")
    prefilter: PrefilterConfig = PrefilterConfig()
    score: ScoreConfig = ScoreConfig(provider="bm25")
    llm: LLMConfig = LLMConfig()
    plan: PlanConfig = PlanConfig()
    attach: AttachConfig = AttachConfig()
    chunk: ChunkConfig = ChunkConfig()
    select: SelectConfig = SelectConfig()
    research: ResearchConfig = ResearchConfig()
    catalog: CatalogConfig = CatalogConfig()
    questions: QuestionsConfig = QuestionsConfig()
    run: RunConfig = RunConfig()
    write: WritingOptions = WritingOptions()
    server: ServerConfig = ServerConfig()
    auth: AuthConfig = AuthConfig()

    @model_validator(mode="after")
    def check_blocks(self) -> "Settings":
        for name in ("search", "fetch", "prefilter", "score", "llm"):
            block: Provider = getattr(self, name)
            if block.release == "ollama" and not block.model:
                raise ValueError(f"{name}.model must be set when {name}.release is 'ollama'")
        if self.fetch.page_timeout >= self.fetch.timeout:
            raise ValueError(
                f"fetch.page_timeout ({self.fetch.page_timeout}) must be below fetch.timeout ({self.fetch.timeout})"
            )
        return self


# Profiles


def config_dir(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", Path.home())) / ".config")
    return Path(base) / "wosarcher"


def list_profiles(env: Mapping[str, str]) -> dict[str, Path]:
    """Every profile file by name."""
    return {path.stem: path for path in sorted((config_dir(env) / "profiles").glob("*.toml"))}


def stored_profile(env: Mapping[str, str]) -> str | None:
    current = config_dir(env) / "current"
    name = current.read_text(encoding="utf-8").strip() if current.is_file() else ""
    return name or None


def store_profile(name: str, env: Mapping[str, str]) -> None:
    available = list_profiles(env)
    if name not in available:
        raise unknown_profile(name, available, env)
    current = config_dir(env) / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(name + "\n", encoding="utf-8")


def select_profile(option: str | None, env: Mapping[str, str]) -> str:
    """`--profile`, then `WOSARCHER_PROFILE`, then `wosarcherd profile use`, then the first profile by name."""
    chosen = option or env.get(ENV_PREFIX + "PROFILE") or stored_profile(env)
    if chosen:
        return chosen
    available = list_profiles(env)
    if not available:
        raise no_profiles(env)
    return next(iter(available))


def no_profiles(env: Mapping[str, str]) -> ConfigError:
    return ConfigError(f"no profiles; add one in {config_dir(env) / 'profiles'}")


def unknown_profile(name: str, available: Mapping[str, object], env: Mapping[str, str]) -> ConfigError:
    if not available:
        return ConfigError(f"unknown profile '{name}'; {no_profiles(env)}")
    return ConfigError(f"unknown profile '{name}'; available: {', '.join(available)}")


def read_toml(kind: str, path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"{kind} {path}: {error}") from None


def pop_description(kind: str, path: Path, data: dict[str, Any]) -> str:
    """The file's one-line `description`, removed from `data`; it is file metadata, not a setting."""
    description = data.pop("description", "")
    if not isinstance(description, str):
        raise ConfigError(f"{kind} {path}: description must be a string")
    return description


def owner(key: str) -> str | None:
    """Who owns a dotted key when a profile or the environment may not set it."""
    if key in DEPTH_KEYS:
        return "depth presets own"
    if any(key == owned or key.startswith(owned + ".") for owned in MODEL_FIELDS.values()):
        return "the model owns (models.<id> in its llm entry or the profile)"
    if key.split(".")[0] in BLOCKS and key not in PROFILE_BLOCK_KEYS:
        return "provider entries own"
    return None


def check_use(where: str, use: object) -> dict[str, str]:
    """A `[use]` table: block names to entry names."""
    if not isinstance(use, Mapping):
        raise ConfigError(f"{where}: use must be a table of block = entry name")
    out: dict[str, str] = {}
    for block, name in cast(Mapping[str, object], use).items():
        if block not in BLOCKS:
            raise ConfigError(f"{where}: use.{block} is not a block; choose from {', '.join(BLOCKS)}")
        if not isinstance(name, str | int) or isinstance(name, bool) or not str(name):
            raise ConfigError(f"{where}: use.{block} must be an entry name")
        out[block] = str(name)
    return out


class Profile(NamedTuple):
    name: str
    path: Path
    description: str
    use: dict[str, str]
    data: dict[str, Any]
    """The profile's own settings, without `description`, `[use]`, and `models`."""
    models: dict[str, dict[str, Any]]
    """The profile's tuning per model ID, shaped like an llm entry's `models` table."""


def read_profile(name: str, env: Mapping[str, str]) -> Profile:
    """The profile file, its keys checked against the keys a profile may set."""
    available = list_profiles(env)
    if name not in available:
        raise unknown_profile(name, available, env)
    return profile_from(name, available[name], read_toml("profile", available[name]))


def profile_from(name: str, path: Path, data: dict[str, Any]) -> Profile:
    """A profile's parsed keys, checked against the keys a profile may set."""
    description = pop_description("profile", path, data)
    use = check_use(f"profile {path}", data.pop("use", {}))
    models = check_models(f"profile {path}", data.pop("models", {}))
    for key in leaf_keys(data):
        found = owner(key)
        if found:
            raise ConfigError(f"profile {path}: {key} cannot be set by a profile; {found} it")
    return Profile(name, path, description, use, data, models)


def check_models(where: str, models: object) -> dict[str, dict[str, Any]]:
    """A `models` table (an llm entry's or a profile's): model ID to the MODEL_FIELDS it sets."""
    if not isinstance(models, Mapping):
        raise ConfigError(f"{where}: models must be a table of model tables")
    checked: dict[str, dict[str, Any]] = {}
    for model, values in cast(Mapping[str, object], models).items():
        if not isinstance(values, Mapping):
            raise ConfigError(f"{where}: models.{model} must be a table")
        table = dict(cast(Mapping[str, Any], values))
        unknown = [key for key in table if key not in MODEL_FIELDS]
        if unknown:
            allowed = ", ".join(MODEL_FIELDS)
            raise ConfigError(f"{where}: models.{model}: {', '.join(unknown)} cannot be set; a model sets {allowed}")
        checked[model] = table
    return checked


# Provider entries: `providers/<block>/<name>.toml`, plus built-in entries that need no file.

BUILTIN_ENTRIES: dict[str, dict[str, dict[str, Any]]] = {
    "prefilter": {"bm25": {"provider": "bm25"}, "none": {"provider": "none"}},
    "score": {"bm25": {"provider": "bm25"}},
}


class Entry(NamedTuple):
    block: str
    name: str
    source: Literal["builtin", "user"]
    path: Path | None
    """None for a built-in entry."""

    @property
    def label(self) -> str:
        return f"entry {self.path}" if self.path else f"built-in entry {self.block}/{self.name}"


class EntryData(NamedTuple):
    entry: Entry
    description: str
    settings: dict[str, Any]
    """The block's fields, without `description` and `models`."""
    models: dict[str, dict[str, Any]]
    """An llm entry's `models` table by model ID."""


def list_entries(env: Mapping[str, str]) -> dict[str, dict[str, Entry]]:
    """Every entry per block, by name; a user file replaces the built-in entry with the same name."""
    found: dict[str, dict[str, Entry]] = {block: {} for block in BLOCKS}
    for block, names in BUILTIN_ENTRIES.items():
        found[block] = {name: Entry(block, name, "builtin", None) for name in names}
    root = config_dir(env) / "providers"
    for directory in sorted(root.iterdir()) if root.is_dir() else []:
        if not directory.is_dir():
            continue
        if directory.name not in BLOCKS:
            raise ConfigError(f"{directory}: providers/{directory.name} is not a block; use {', '.join(BLOCKS)}")
        for path in sorted(directory.glob("*.toml")):
            found[directory.name][path.stem] = Entry(directory.name, path.stem, "user", path)
    return {block: dict(sorted(entries.items())) for block, entries in found.items()}


def unknown_entry(block: str, name: str, available: Mapping[str, object]) -> ConfigError:
    return ConfigError(f"unknown {block} entry '{name}'; {block} entries: {', '.join(available) or 'none'}")


def find_entry(block: str, name: str, env: Mapping[str, str]) -> Entry:
    if block not in BLOCKS:
        raise ConfigError(f"unknown block '{block}'; choose from {', '.join(BLOCKS)}")
    available = list_entries(env)[block]
    if name not in available:
        raise unknown_entry(block, name, available)
    return available[name]


def entry_owner(block: str, key: str) -> str | None:
    """Who owns a key of an entry file when the entry may not set it."""
    full = f"{block}.{key}"
    if full in DEPTH_KEYS:
        return "depth presets own"
    if full in PROFILE_BLOCK_KEYS and full != "llm.model":
        return "profiles own"
    if block == "llm" and key.split(".")[0] in ("context_window", "max_output_tokens", "reasoning"):
        return "the model owns (set it under models.<id>)"
    return None


def read_entry(entry: Entry) -> EntryData:
    """The entry's fields, checked against the keys an entry may set."""
    if entry.path is None:
        return EntryData(entry, "", dict(BUILTIN_ENTRIES[entry.block][entry.name]), {})
    path = entry.path
    data = read_toml("entry", path)
    description = pop_description("entry", path, data)
    models: object = data.pop("models", {})
    if models and entry.block != "llm":
        raise ConfigError(f"entry {path}: models: only llm entries list models")
    checked_models = check_models(f"entry {path}", models)
    for key in leaf_keys(data):
        found = entry_owner(entry.block, key)
        if found:
            raise ConfigError(f"entry {path}: {key} cannot be set by a provider entry; {found} it")
    return EntryData(entry, description, data, checked_models)


def pick_entries(
    entries: Mapping[str, Mapping[str, Entry]], *choices: Mapping[str, str], blocks: tuple[str, ...] = BLOCKS
) -> dict[str, Entry]:
    """One entry per block: the last choice that names one wins; a block with one entry needs no choice."""
    chosen: dict[str, Entry] = {}
    for block in blocks:
        available = entries[block]
        name = next((choice[block] for choice in reversed(choices) if block in choice), None)
        if name is None:
            if len(available) != 1:
                listed = ", ".join(available) or "none"
                raise ConfigError(
                    f"choose a {block} entry ([use] in the profile or --use {block}=NAME); {block} entries: {listed}"
                )
            name = next(iter(available))
        if name not in available:
            raise unknown_entry(block, name, available)
        chosen[block] = available[name]
    return chosen


# Layers: each is a nested dict plus the source of every leaf key.

Layer = tuple[dict[str, Any], dict[str, str]]


def parse_value(raw: str) -> Any:
    """A TOML value (`12`, `true`, `[..]`, `"x"`); anything else is a plain string."""
    try:
        return tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        return raw


def set_path(tree: dict[str, Any], path: list[str], value: Any) -> None:
    for key in path[:-1]:
        tree = tree.setdefault(key, {})
    tree[path[-1]] = value


def leaf_keys(tree: Mapping[str, Any], prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, value in tree.items():
        if isinstance(value, Mapping):
            keys.extend(leaf_keys(value, f"{prefix}{key}."))  # pyright: ignore[reportUnknownArgumentType]
        else:
            keys.append(prefix + key)
    return keys


def labelled(tree: dict[str, Any], label: str) -> Layer:
    return tree, {key: label for key in leaf_keys(tree)}


def entries_layer(loaded: Mapping[str, EntryData]) -> Layer:
    """Each block replaced whole by its entry."""
    tree: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for block, data in loaded.items():
        tree[block] = data.settings
        sources.update({f"{block}.{key}": data.entry.label for key in leaf_keys(data.settings)})
    return tree, sources


def model_tree(models: Mapping[str, Mapping[str, Any]], model: str) -> dict[str, Any]:
    """The values `models.<model>` sets, at their keys; empty when the table does not list the model."""
    tree: dict[str, Any] = {}
    for field, value in models.get(model, {}).items():
        set_path(tree, MODEL_FIELDS[field].split("."), value)
    return tree


def model_layer(llm: EntryData, model: str) -> Layer:
    return labelled(model_tree(llm.models, model), f"{llm.entry.label} models.{model}")


def profile_model_layer(profile: Profile, model: str) -> Layer:
    return labelled(model_tree(profile.models, model), f"profile {profile.path} models.{model}")


def model_defaults() -> dict[str, Any]:
    """The built-in values of every model-owned key, for a model no entry lists."""
    defaults = Settings()
    return {
        "llm": {
            "context_window": defaults.llm.context_window,
            "max_output_tokens": defaults.llm.max_output_tokens,
            "reasoning": defaults.llm.reasoning.model_dump(),
        },
        "research": {"gap_context_tokens": defaults.research.gap_context_tokens},
    }


def env_layer(env: Mapping[str, str]) -> tuple[Layer, dict[str, str]]:
    """`WOSARCHER_SELECT__MAX_CONTEXT_TOKENS=x` sets `select.max_context_tokens`, and the entry choices.

    Values stay strings except lists (`[..]`). Only keys a profile may set are allowed, plus
    `WOSARCHER_USE__<BLOCK>`.
    """
    tree: dict[str, Any] = {}
    sources: dict[str, str] = {}
    use: dict[str, str] = {}
    for name, raw in sorted(env.items()):
        if not name.startswith(ENV_PREFIX) or name == ENV_PREFIX + "PROFILE" or name in CLIENT_ENV:
            continue
        path = name.removeprefix(ENV_PREFIX).lower().split("__")
        key = ".".join(path)
        if path[0] == "use":
            use.update(check_use(f"environment variable {name}", {".".join(path[1:]): raw}))
            continue
        found = owner(key)
        if found:
            raise ConfigError(f"environment variable {name}: {key} cannot be set by the environment; {found} it")
        set_path(tree, path, parse_value(raw) if raw.startswith("[") else raw)
        sources[key] = f"environment variable {name}"
    return (tree, sources), use


def override_layer(overrides: list[str]) -> tuple[Layer, dict[str, str]]:
    """`--set` values (any key), and the run's entry choices given as `use.<block>=<name>`."""
    tree: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for override in overrides:
        key, sep, raw = override.partition("=")
        if not sep or not key.strip():
            raise ConfigError(f"override '{override}' must look like dotted.key=value")
        path = key.strip().split(".")
        set_path(tree, path, parse_value(raw.strip()))
        sources[".".join(path)] = f"override --set {override}"
    use = check_use("--use", tree.pop("use", {}))
    return (tree, sources), use


def use_overrides(use: Mapping[str, str]) -> list[str]:
    """Entry choices as the overrides a run records (`use.<block>=<name>`)."""
    return [f"use.{block}={name}" for block, name in use.items()]


def without_use(overrides: list[str]) -> list[str]:
    return [override for override in overrides if not override.strip().startswith("use.")]


def deep_merge(base: dict[str, Any], top: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in top.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)  # pyright: ignore[reportUnknownArgumentType]
        else:
            merged[key] = value
    return merged


def source_of(location: str, sources: Mapping[str, str]) -> str:
    """The source of a field, or of its closest set parent or child."""
    parts = location.split(".")
    for end in range(len(parts), 0, -1):
        prefix = ".".join(parts[:end])
        if prefix in sources:
            return sources[prefix]
    children = [source for key, source in sources.items() if key.startswith(location + ".")]
    return children[0] if children else "built-in defaults"


def tree_get(tree: Mapping[str, Any], key: str) -> Any:
    found: Any = tree
    for part in key.split("."):
        if not isinstance(found, Mapping) or part not in found:
            return None
        found = cast(Mapping[str, Any], found)[part]
    return found


class Resolved(NamedTuple):
    settings: Settings
    use: dict[str, str]
    """The entry name chosen for each block."""


def resolve_run(
    profile: str | None, overrides: list[str], env: Mapping[str, str], depth: str | None = None
) -> Resolved:
    """The run's settings and entries; `use.<block>=<name>` overrides choose entries for this run."""
    chosen_profile = read_profile(select_profile(profile, env), env)
    env_values, env_use = env_layer(env)
    run_values, run_use = override_layer(overrides)
    chosen = pick_entries(list_entries(env), chosen_profile.use, env_use, run_use)
    loaded = {block: read_entry(entry) for block, entry in chosen.items()}
    model = str(
        tree_get(run_values[0], "llm.model")
        or tree_get(env_values[0], "llm.model")
        or tree_get(chosen_profile.data, "llm.model")
        or loaded["llm"].settings.get("model")
        or ""
    )
    layers = [
        entries_layer(loaded),
        model_layer(loaded["llm"], model),
        profile_model_layer(chosen_profile, model),
        labelled(chosen_profile.data, f"profile {chosen_profile.path}"),
        env_values,
    ]
    if depth is not None and depth != CUSTOM_DEPTH:
        layers.append(depth_layer(*load_depth(depth, env)))
    settings = load_secrets(validate([*layers, run_values]))
    return Resolved(settings, {block: entry.name for block, entry in chosen.items()})


def resolve(profile: str | None, overrides: list[str], env: Mapping[str, str], depth: str | None = None) -> Settings:
    return resolve_run(profile, overrides, env, depth).settings


def resolve_server(env: Mapping[str, str]) -> Settings:
    """What `wosarcherd serve` and `auth` need: defaults < the active profile's own keys < environment.

    Needs no profile and no entry, so a fresh install can serve.
    """
    layers: list[Layer] = []
    if list_profiles(env) or env.get(ENV_PREFIX + "PROFILE") or stored_profile(env):
        found = read_profile(select_profile(None, env), env)
        layers.append(labelled(found.data, f"profile {found.path}"))
    return load_secrets(validate([*layers, env_layer(env)[0]]))


def own_settings(profile: str, env: Mapping[str, str]) -> dict[str, Any]:
    """What the profile and the environment set, as flat dotted keys, before validation."""
    tree = deep_merge(read_profile(profile, env).data, env_layer(env)[0][0])
    return depth_values(tree)


def entry_settings(block: str, name: str, env: Mapping[str, str], gpu_policy: str = "shared") -> Settings:
    """Defaults with one entry in its block (an llm entry with its default model's values)."""
    data = read_entry(find_entry(block, name, env))
    layers = [entries_layer({block: data}), labelled({"run": {"gpu_policy": gpu_policy}}, "the profile")]
    if block == "llm":
        layers.insert(1, model_layer(data, str(data.settings.get("model", ""))))
    return load_secrets(validate(layers))


def entry_block(data: EntryData) -> Provider:
    """The entry validated as its block, defaults filled in; secrets are not read."""
    block: Provider = getattr(validate([entries_layer({data.entry.block: data})]), data.entry.block)
    return block


# Depth presets


class Depth(NamedTuple):
    name: str
    path: Path
    source: Literal["builtin", "user"]


def list_depths(env: Mapping[str, str] | None = None) -> dict[str, Depth]:
    """The built-in presets in DEPTH_ORDER, then the user's (`$XDG_CONFIG_HOME/wosarcher/depths/`) by name."""
    order = {name: index for index, name in enumerate(DEPTH_ORDER)}
    builtin = sorted(BUILTIN_DEPTHS.glob("*.toml"), key=lambda path: (order.get(path.stem, len(order)), path.stem))
    found = {path.stem: Depth(path.stem, path, "builtin") for path in builtin}
    user = config_dir(env) / "depths" if env is not None else None
    for path in sorted(user.glob("*.toml")) if user is not None else []:
        if path.stem in found or path.stem == CUSTOM_DEPTH:
            raise ConfigError(f"depth {path}: {path.stem} is a built-in depth name; rename the file")
        found[path.stem] = Depth(path.stem, path, "user")
    return found


def unknown_depth(name: str, available: Mapping[str, object]) -> ConfigError:
    return ConfigError(f"unknown depth '{name}'; available: {', '.join(available)}")


def read_depth(name: str, env: Mapping[str, str] | None = None) -> tuple[Depth, str, dict[str, Any]]:
    """The preset, its description, and its settings; any key outside DEPTH_KEYS fails."""
    available = list_depths(env)
    if name not in available:
        raise unknown_depth(name, available)
    depth = available[name]
    data = read_toml("depth", depth.path)
    description = pop_description("depth", depth.path, data)
    for key in leaf_keys(data):
        if key not in DEPTH_KEYS:
            raise ConfigError(f"depth {depth.path}: {key} cannot be set by a depth preset")
    return depth, description, data


def load_depth(name: str, env: Mapping[str, str] | None = None) -> tuple[Path, dict[str, Any]]:
    depth, _, data = read_depth(name, env)
    return depth.path, data


def depth_values(data: Mapping[str, Any]) -> dict[str, Any]:
    """The preset's settings as flat dotted keys."""
    out: dict[str, Any] = {}
    for key in leaf_keys(data):
        value: Any = data
        for part in key.split("."):
            value = value[part]
        out[key] = value
    return out


def depth_layer(path: Path, data: dict[str, Any]) -> Layer:
    return labelled(data, f"depth {path}")


def validate(layers: list[Layer]) -> Settings:
    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for tree, layer_sources in layers:
        merged = deep_merge(merged, tree)
        sources.update(layer_sources)
    try:
        return Settings.model_validate(merged)
    except ValidationError as error:
        lines: list[str] = []
        for problem in error.errors():
            location = ".".join(str(part) for part in problem["loc"])
            if not location:
                lines.append(problem["msg"])
                continue
            lines.append(f"{location}: {problem['msg']} (from {source_of(location, sources)})")
        raise ConfigError("invalid configuration:\n" + "\n".join(lines)) from None


# Secret sources: `<x>_file` and `<x>_command` fill the secret `<x>`.

SECRET_SUFFIXES = ("_file", "_command")
COMMAND_TIMEOUT = 10.0


def read_secret_file(key: str, path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").removesuffix("\n")
    except OSError as error:
        raise ConfigError(f"{key}: cannot read {path}: {error.strerror or type(error).__name__}") from None
    except UnicodeDecodeError:
        raise ConfigError(f"{key}: {path} is not UTF-8") from None


def run_secret_command(key: str, argv: list[str]) -> str:
    """Standard output of `argv`, run without a shell; errors never include the output."""
    name = argv[0] if argv else ""
    if not argv:
        raise ConfigError(f"{key}: the command is empty")
    try:
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=COMMAND_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise ConfigError(f"{key}: {name} did not finish within {COMMAND_TIMEOUT:g} seconds") from None
    except OSError as error:
        raise ConfigError(f"{key}: cannot run {name}: {error.strerror or type(error).__name__}") from None
    if done.returncode != 0:
        raise ConfigError(f"{key}: {name} exited with status {done.returncode}")
    try:
        return done.stdout.decode("utf-8").removesuffix("\n")
    except UnicodeDecodeError:
        raise ConfigError(f"{key}: {name} printed output that is not UTF-8") from None


def load_block(prefix: str, block: BaseModel) -> BaseModel:
    update: dict[str, Any] = {}
    for name, field in type(block).model_fields.items():
        if not is_secret(field.annotation):
            continue
        path: str | None = getattr(block, f"{name}_file", None)
        argv: list[str] | None = getattr(block, f"{name}_command", None)
        if path is not None:
            update[name] = SecretStr(read_secret_file(f"{prefix}{name}_file", path))
        elif argv is not None:
            update[name] = SecretStr(run_secret_command(f"{prefix}{name}_command", argv))
    return block.model_copy(update=update) if update else block


def load_secrets(settings: Settings) -> Settings:
    """Settings with every secret given as a file or a command read once."""
    update: dict[str, Any] = {}
    for name in type(settings).model_fields:
        block = getattr(settings, name)
        if isinstance(block, BaseModel):
            loaded = load_block(f"{name}.", block)
            if loaded is not block:
                update[name] = loaded
    return settings.model_copy(update=update) if update else settings


def drop_sources(tree: Mapping[str, Any]) -> dict[str, Any]:
    """`tree` without `*_file` and `*_command` keys, at any depth."""
    out: dict[str, Any] = {}
    for key, value in tree.items():
        if key.endswith(SECRET_SUFFIXES):
            continue
        out[key] = drop_sources(value) if isinstance(value, Mapping) else value  # pyright: ignore[reportUnknownArgumentType]
    return out


# Hooks: `hooks.toml` next to the profiles; never part of `Settings`, so no override reaches it.

HOOKS_FILE = "hooks.toml"


class HeaderValue(Block):
    """A webhook header: a string, or a table with one of `value`, `value_file`, `value_command`."""

    value: SecretStr | None = None
    value_file: str | None = None
    value_command: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def from_string(cls, data: object) -> object:
        return {"value": data} if isinstance(data, str) else data

    @model_validator(mode="after")
    def check_value(self) -> "HeaderValue":
        check_one_source(self, "value")
        if self.value is None and self.value_file is None and self.value_command is None:
            raise ValueError("set one of value, value_file, value_command")
        return self


class HookEntry(Block):
    """One `[[on_finish]]` table: a webhook (`url`) or a command (`command`)."""

    url: str | None = None
    command: list[str] | None = None
    status: list[FinishedStatus] = Field(default=["done", "failed", "cancelled"], min_length=1)
    timeout: float = Field(default=10.0, gt=0)
    headers: dict[str, HeaderValue] = {}
    secret: SecretStr | None = None
    secret_file: str | None = None
    secret_command: list[str] | None = None

    @property
    def kind(self) -> Literal["webhook", "command"]:
        return "webhook" if self.url is not None else "command"

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str | None) -> str | None:
        if value is not None:
            parts = urlsplit(value)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                raise ValueError("url must be an http or https URL")
        return value

    @field_validator("command")
    @classmethod
    def check_command(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and not value:
            raise ValueError("command must not be empty")
        return value

    @model_validator(mode="after")
    def check_kind(self) -> "HookEntry":
        if (self.url is None) == (self.command is None):
            raise ValueError("set exactly one of url, command")
        if self.command is not None:
            webhook_only = ["headers"] if self.headers else []
            webhook_only += [key for key in ("secret", "secret_file", "secret_command") if getattr(self, key)]
            if webhook_only:
                raise ValueError(f"{', '.join(webhook_only)}: only a url hook may set this")
        check_one_source(self, "secret")
        return self


class HooksFile(Block):
    on_finish: list[HookEntry] = []


def load_hooks(env: Mapping[str, str]) -> list[HookEntry]:
    """Every `[[on_finish]]` entry of `hooks.toml`, validated; none when the file is missing."""
    path = config_dir(env) / HOOKS_FILE
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"{path}: {error}") from None
    try:
        return HooksFile.model_validate(data).on_finish
    except ValidationError as error:
        lines: list[str] = []
        for problem in error.errors():
            loc = list(problem["loc"])
            where = ".".join(str(part) for part in loc)
            if len(loc) >= 2 and loc[0] == "on_finish" and isinstance(loc[1], int):
                key = ".".join(str(part) for part in loc[2:])
                where = f"entry {loc[1] + 1}" + (f", {key}" if key else "")
            lines.append(f"{where}: {problem['msg']}")
        raise ConfigError(f"{path}: invalid hooks:\n" + "\n".join(lines)) from None


def resolve_hook(index: int, entry: HookEntry) -> HookEntry:
    """`entry` with its secret and header values read from their files or commands."""
    prefix = f"{HOOKS_FILE} entry {index}: "
    headers = {
        name: cast(HeaderValue, load_block(f"{prefix}headers.{name}.", value)) for name, value in entry.headers.items()
    }
    loaded = cast(HookEntry, load_block(prefix, entry))
    return loaded.model_copy(update={"headers": headers})


# Redaction


def is_secret(annotation: object) -> bool:
    return annotation is SecretStr or SecretStr in get_args(annotation)


def redact(model: BaseModel) -> dict[str, Any]:
    """JSON-ready dict with every set secret as `***` and every unset secret as empty."""
    out: dict[str, Any] = {}
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        if isinstance(value, BaseModel):
            out[name] = redact(value)
        elif is_secret(field.annotation):
            out[name] = "***" if value is not None else ""
        else:
            out[name] = to_jsonable_python(value)
    return out


def unredact(saved: Mapping[str, Any], model: BaseModel) -> dict[str, Any]:
    """`saved` with each `***` secret taken from `model` and each empty one unset."""
    out = dict(saved)
    for name, field in type(model).model_fields.items():
        if name not in out:
            continue
        value = getattr(model, name)
        if isinstance(value, BaseModel) and isinstance(out[name], Mapping):
            out[name] = unredact(out[name], value)
        elif is_secret(field.annotation) and out[name] == "***":
            out[name] = value
        elif is_secret(field.annotation) and out[name] == "":
            out[name] = None
    return out


def prune_unknown(
    saved: Mapping[str, Any], model_type: type[BaseModel], prefix: str = ""
) -> tuple[dict[str, Any], list[str]]:
    """`saved` without keys `model_type` does not know, and those keys as dotted paths."""
    out: dict[str, Any] = {}
    dropped: list[str] = []
    fields = model_type.model_fields
    for key, value in saved.items():
        if key not in fields:
            dropped.append(f"{prefix}{key}")
            continue
        annotation = fields[key].annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, Mapping):
            out[key], inner = prune_unknown(value, annotation, f"{prefix}{key}.")  # pyright: ignore[reportUnknownArgumentType]
            dropped.extend(inner)
        else:
            out[key] = value
    return out, dropped


def fork_settings(
    saved: Mapping[str, Any],
    parent_use: Mapping[str, str],
    use: Mapping[str, str],
    overrides: list[str],
    env: Mapping[str, str],
    parent_profile: str | None = None,
) -> tuple[Resolved, list[str]]:
    """A fork's settings: the parent's saved (redacted) settings, then `use` and `overrides` on top.

    Secrets come from the current entries the parent used. A block in `use` is replaced by
    that entry's fields (profile and depth keys stay as saved); for `llm`, the chosen
    model's values apply again: the entry's `models.<id>`, then the parent profile's as
    its file is now (nothing when the profile is gone). They also apply when the fork's
    model (`llm.model` override, else the `use.llm` entry's, else the saved one) differs
    from the saved model. Keys the current `Settings` does not know are dropped and
    returned as dotted paths. Saved `*_file` and `*_command` keys are ignored.
    """
    pruned, dropped = prune_unknown(saved, Settings)
    entries = list_entries(env)
    names = {**parent_use, **use}
    for block, name in names.items():
        if block not in BLOCKS:
            raise ConfigError(f"unknown block '{block}'; choose from {', '.join(BLOCKS)}")
        if name not in entries[block]:
            raise unknown_entry(block, name, entries[block])
    loaded = {block: read_entry(entries[block][name]) for block, name in names.items()}
    current = validate([entries_layer(loaded)])
    tree = unredact(drop_sources(pruned), load_secrets(current))
    sources: dict[str, str] = {}
    for block in use:
        kept = {key: value for key, value in tree.get(block, {}).items() if entry_owner(block, key) == "profiles own"}
        tree[block] = {**loaded[block].settings, **kept}
        sources.update({f"{block}.{key}": loaded[block].entry.label for key in leaf_keys(loaded[block].settings)})
    run_values, run_use = override_layer(overrides)
    if run_use:
        raise ConfigError("a fork chooses entries with --use, not --set use.<block>")
    saved_model = str(tree_get(tree, "llm.model") or "")
    entry_model = loaded["llm"].settings.get("model") if "llm" in use else None
    model = str(tree_get(run_values[0], "llm.model") or entry_model or saved_model)
    if "llm" in use or model != saved_model:
        tuning = deep_merge(model_defaults(), model_tree(loaded["llm"].models, model))
        if parent_profile is not None and parent_profile in list_profiles(env):
            tuning = deep_merge(tuning, model_tree(read_profile(parent_profile, env).models, model))
        tree = deep_merge(tree, tuning)
        tree["llm"]["model"] = model
    settings = load_secrets(validate([(tree, sources), run_values]))
    return Resolved(settings, dict(names)), dropped


def toml_key(key: str) -> str:
    """A bare key when TOML allows one, else a quoted key (`"qwen3.5:9b"`)."""
    return key if BARE_KEY.fullmatch(key) else json.dumps(key)


def to_toml(tree: Mapping[str, Any], prefix: str = "") -> str:
    """Render a redacted settings dict as TOML; `None` values are omitted."""
    scalars: list[str] = []
    tables: list[str] = []
    for key, value in tree.items():
        if isinstance(value, Mapping):
            name = f"{prefix}{toml_key(key)}"
            body = to_toml(value, f"{name}.")  # pyright: ignore[reportUnknownArgumentType]
            tables.append(f"[{name}]\n{body}")
        elif value is not None:
            scalars.append(f"{toml_key(key)} = {json.dumps(value)}")
    head = "\n".join(scalars)
    return "\n".join(part for part in [head + "\n" if head else "", *tables] if part)

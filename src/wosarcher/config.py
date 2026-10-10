"""Run configuration: settings models, profiles, precedence, and secret redaction.

`resolve()` is the whole story: pick a profile, then merge built-in defaults <
profile < `WOSARCHER_*` environment < depth preset < `--set` overrides, and
validate once.
"""

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, cast, get_args

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

from wosarcher.models import Effort, Stage, WritingOptions, domain_list, search_language

DEFAULT_PROFILE = "workstation"
ENV_PREFIX = "WOSARCHER_"
BUILTIN_PROFILES = Path(__file__).parent / "profiles"
BUILTIN_DEPTHS = Path(__file__).parent / "depths"
DEPTH_ORDER = ("quick", "standard", "deep", "exhaustive")
CUSTOM_DEPTH = "custom"

# Typed research fields (CLI flags, `RunCreate.research`) and the key each sets.
RESEARCH_KEYS = {
    "sub_queries": "plan.max_sub_queries",
    "results_per_query": "search.max_results",
    "max_pages": "fetch.max_pages",
    "passages_per_query": "score.top_k",
    "context_tokens": "select.max_context_tokens",
    "gap_context_tokens": "research.gap_context_tokens",
    "rounds": "research.rounds",
    "queries_per_round": "research.queries_per_round",
}
# The only keys a depth preset may set, besides its `description`.
DEPTH_KEYS = (*RESEARCH_KEYS.values(), "write.words")

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
}

# Concurrency per adapter when a block leaves `concurrency` unset.
DEFAULT_CONCURRENCY = {"searxng": 4, "firecrawl": 6, "embeddings": 4, "rerank": 4, "jev": 64, "openai": 1}


class ConfigError(Exception):
    pass


class Block(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Prices(Block):
    input_per_mtok: float | None = None
    output_per_mtok: float | None = None
    per_unit: float | None = None


class Provider(Block):
    """The shape every provider block shares."""

    provider: str
    base_url: str = ""
    api_key: SecretStr | None = None
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


class PrefilterConfig(Provider):
    provider: str = "bm25"
    top_k: int = Field(default=50, gt=0)
    context: Literal["header", "body"] = "header"


class ReasoningConfig(Block):
    """Thinking effort per LLM step; see `models.Effort`."""

    plan: Effort = "none"
    gap: Effort = "none"
    write: Effort = "none"


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


class AuthConfig(Block):
    password_hash: SecretStr | None = None
    """None: the hash in `auth.json`, or no password at all."""
    session_days: int = Field(default=30, gt=0)
    allowed_origins: list[str] = []
    """Origins besides the server's own that may send state-changing requests."""


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


def list_profiles(env: Mapping[str, str]) -> dict[str, tuple[Path, Literal["built-in", "user"]]]:
    """Every profile by name; a user file replaces the built-in one with the same name."""
    found: dict[str, tuple[Path, Literal["built-in", "user"]]] = {
        path.stem: (path, "built-in") for path in sorted(BUILTIN_PROFILES.glob("*.toml"))
    }
    user = config_dir(env) / "profiles"
    found.update({path.stem: (path, "user") for path in sorted(user.glob("*.toml"))})
    return dict(sorted(found.items()))


def stored_profile(env: Mapping[str, str]) -> str | None:
    current = config_dir(env) / "current"
    name = current.read_text(encoding="utf-8").strip() if current.is_file() else ""
    return name or None


def store_profile(name: str, env: Mapping[str, str]) -> None:
    available = list_profiles(env)
    if name not in available:
        raise unknown_profile(name, available)
    current = config_dir(env) / "current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(name + "\n", encoding="utf-8")


def select_profile(option: str | None, env: Mapping[str, str]) -> str:
    """`--profile`, then `WOSARCHER_PROFILE`, then `wosarcher profile use`, then the default."""
    return option or env.get(ENV_PREFIX + "PROFILE") or stored_profile(env) or DEFAULT_PROFILE


def unknown_profile(name: str, available: Mapping[str, object]) -> ConfigError:
    return ConfigError(f"unknown profile '{name}'; available: {', '.join(available)}")


def read_profile(name: str, env: Mapping[str, str]) -> tuple[Path, dict[str, Any]]:
    """The profile file as written, `description` included."""
    available = list_profiles(env)
    if name not in available:
        raise unknown_profile(name, available)
    path = available[name][0]
    try:
        return path, tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"profile {path}: {error}") from error


def load_profile(name: str, env: Mapping[str, str]) -> tuple[Path, dict[str, Any]]:
    """The profile's settings; the top-level `description` is file metadata, not a setting."""
    path, data = read_profile(name, env)
    data.pop("description", None)
    return path, data


def profile_description(name: str, env: Mapping[str, str]) -> str:
    """The profile's one-line `description`, empty when it sets none."""
    path, data = read_profile(name, env)
    description = data.get("description", "")
    if not isinstance(description, str):
        raise ConfigError(f"profile {path}: description must be a string")
    return description


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


def profile_layer(path: Path, data: dict[str, Any]) -> Layer:
    return data, {key: f"profile {path}" for key in leaf_keys(data)}


def env_layer(env: Mapping[str, str]) -> Layer:
    """`WOSARCHER_SCORE__API_KEY=x` sets `score.api_key`. Values stay strings except lists (`[..]`)."""
    tree: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for name, raw in sorted(env.items()):
        if not name.startswith(ENV_PREFIX) or name == ENV_PREFIX + "PROFILE":
            continue
        path = name.removeprefix(ENV_PREFIX).lower().split("__")
        set_path(tree, path, parse_value(raw) if raw.startswith("[") else raw)
        sources[".".join(path)] = f"environment variable {name}"
    return tree, sources


def override_layer(overrides: list[str]) -> Layer:
    tree: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for override in overrides:
        key, sep, raw = override.partition("=")
        if not sep or not key.strip():
            raise ConfigError(f"override '{override}' must look like dotted.key=value")
        path = key.strip().split(".")
        set_path(tree, path, parse_value(raw.strip()))
        sources[".".join(path)] = f"override --set {override}"
    return tree, sources


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


def resolve(profile: str | None, overrides: list[str], env: Mapping[str, str], depth: str | None = None) -> Settings:
    path, data = load_profile(select_profile(profile, env), env)
    layers = [profile_layer(path, data), env_layer(env)]
    if depth is not None and depth != CUSTOM_DEPTH:
        layers.append(depth_layer(*load_depth(depth)))
    return validate([*layers, override_layer(overrides)])


def own_settings(profile: str, env: Mapping[str, str]) -> dict[str, Any]:
    """What the profile and the environment set, as flat dotted keys, before validation."""
    path, data = load_profile(profile, env)
    tree = deep_merge(profile_layer(path, data)[0], env_layer(env)[0])
    return depth_values(tree)


# Depth presets


def list_depths(directory: Path = BUILTIN_DEPTHS) -> dict[str, Path]:
    """Every preset by name, in DEPTH_ORDER first, then by name."""
    found = {path.stem: path for path in directory.glob("*.toml")}
    order = {name: index for index, name in enumerate(DEPTH_ORDER)}
    return dict(sorted(found.items(), key=lambda item: (order.get(item[0], len(order)), item[0])))


def unknown_depth(name: str, available: Mapping[str, object]) -> ConfigError:
    return ConfigError(f"unknown depth '{name}'; available: {', '.join(available)}")


def read_depth(name: str, directory: Path = BUILTIN_DEPTHS) -> tuple[Path, str, dict[str, Any]]:
    """The preset's path, description, and settings; any key outside DEPTH_KEYS fails."""
    available = list_depths(directory)
    if name not in available:
        raise unknown_depth(name, available)
    path = available[name]
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"depth {path}: {error}") from error
    description = data.pop("description", "")
    if not isinstance(description, str):
        raise ConfigError(f"depth {path}: description must be a string")
    for key in leaf_keys(data):
        if key not in DEPTH_KEYS:
            raise ConfigError(f"depth {path}: {key} cannot be set by a depth preset")
    return path, description, data


def load_depth(name: str, directory: Path = BUILTIN_DEPTHS) -> tuple[Path, dict[str, Any]]:
    path, _, data = read_depth(name, directory)
    return path, data


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
    return data, {key: f"depth {path}" for key in leaf_keys(data)}


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


def restore_secrets(
    saved: Mapping[str, Any], current: Settings, overrides: list[str] | None = None
) -> tuple[Settings, list[str]]:
    """Validate saved (redacted) settings, secrets taken from `current`, then `overrides` on top.

    Keys the current `Settings` does not know are dropped and returned as dotted paths.
    """
    pruned, dropped = prune_unknown(saved, Settings)
    restored = unredact(pruned, current)
    return validate([(restored, {}), override_layer(overrides or [])]), dropped


def to_toml(tree: Mapping[str, Any], prefix: str = "") -> str:
    """Render a redacted settings dict as TOML; `None` values are omitted."""
    scalars: list[str] = []
    tables: list[str] = []
    for key, value in tree.items():
        if isinstance(value, Mapping):
            body = to_toml(value, f"{prefix}{key}.")  # pyright: ignore[reportUnknownArgumentType]
            tables.append(f"[{prefix}{key}]\n{body}")
        elif value is not None:
            scalars.append(f"{key} = {json.dumps(value)}")
    head = "\n".join(scalars)
    return "\n".join(part for part in [head + "\n" if head else "", *tables] if part)

"""Run configuration: settings models, profiles, precedence, and secret redaction.

`resolve()` is the whole story: pick a profile, then merge built-in defaults <
profile < `WOSARCHER_*` environment < `--set` overrides, and validate once.
"""

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_core import to_jsonable_python

from wosarcher.models import Stage, WritingOptions

DEFAULT_PROFILE = "workstation"
ENV_PREFIX = "WOSARCHER_"
BUILTIN_PROFILES = Path(__file__).parent / "profiles"

# Seconds each stage may take; `run.stage_timeouts` overrides single stages.
DEFAULT_STAGE_TIMEOUTS: dict[Stage, float] = {
    "load": 60,
    "plan": 180,
    "search": 120,
    "fetch": 600,
    "chunk": 60,
    "prefilter": 600,
    "score": 900,
    "select": 60,
    "write": 1800,
}

# Concurrency per adapter when a block leaves `concurrency` unset.
DEFAULT_CONCURRENCY = {"searxng": 4, "firecrawl": 6, "embeddings": 4, "rerank": 4, "jev": 64, "llm": 1}


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
    prices: Prices = Prices()


class SearchConfig(Provider):
    max_results: int = Field(default=10, ge=1)
    language: str = ""
    time_range: Literal["", "day", "week", "month", "year"] = ""


class FetchConfig(Provider):
    max_chars: int = Field(default=50000, ge=1)
    only_main_content: bool = True
    page_timeout: float = Field(default=45.0, gt=0)


class ScoreConfig(Provider):
    min_score: float = 1.5
    relative_threshold: float = Field(default=0.5, ge=0, le=1)
    top_k: int = Field(default=10, gt=0)
    fallback: list[Literal["bm25", "passthrough"]] = ["bm25", "passthrough"]


class PrefilterConfig(Provider):
    provider: str = "bm25"
    top_k: int = Field(default=50, gt=0)


class LLMConfig(Provider):
    context_window: int = Field(default=32768, gt=0)
    chars_per_token: float = Field(default=3.5, gt=0)
    token_margin: float = Field(default=1.1, ge=1)


class PlanConfig(Block):
    max_sub_queries: int = Field(default=3, ge=0)


class AttachConfig(Block):
    max_bytes: int = Field(default=5_000_000, gt=0)


class ChunkConfig(Block):
    size: int = Field(default=1000, gt=0)
    overlap: int = Field(default=100, ge=0)

    @model_validator(mode="after")
    def check_overlap(self) -> "ChunkConfig":
        if self.overlap >= self.size:
            raise ValueError(f"chunk.overlap ({self.overlap}) must be below chunk.size ({self.size})")
        return self


class SelectConfig(Block):
    passthrough_chars: int = Field(default=8000, ge=0)
    max_chunks_per_source: int = Field(default=5, gt=0)
    max_context_tokens: int = Field(default=16000, gt=0)
    file_share: float = Field(default=0.5, ge=0, le=1)
    prompt_reserve_tokens: int = Field(default=2000, ge=0)


class RunConfig(Block):
    gpu_policy: Literal["shared", "exclusive"] = "shared"
    runs_dir: Path | None = None
    """None: `$XDG_DATA_HOME/wosarcher/runs`."""
    cache_dir: Path | None = None
    """None: `$XDG_CACHE_HOME/wosarcher`."""
    page_cache_ttl_hours: float = Field(default=24, ge=0)
    """0 disables the page cache."""
    stage_timeouts: dict[Stage, float] = DEFAULT_STAGE_TIMEOUTS

    @field_validator("stage_timeouts", mode="before")
    @classmethod
    def fill_timeouts(cls, value: object) -> object:
        if isinstance(value, Mapping):
            return {**DEFAULT_STAGE_TIMEOUTS, **cast(Mapping[str, object], value)}
        return value


class ServerConfig(Block):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, gt=0, lt=65536)
    max_concurrent_runs: int = Field(default=1, gt=0)
    static_dir: Path = Path("web/dist")


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
    llm: LLMConfig = LLMConfig(provider="llm")
    plan: PlanConfig = PlanConfig()
    attach: AttachConfig = AttachConfig()
    chunk: ChunkConfig = ChunkConfig()
    select: SelectConfig = SelectConfig()
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


def load_profile(name: str, env: Mapping[str, str]) -> tuple[Path, dict[str, Any]]:
    available = list_profiles(env)
    if name not in available:
        raise unknown_profile(name, available)
    path = available[name][0]
    try:
        return path, tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"profile {path}: {error}") from error


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


def resolve(profile: str | None, overrides: list[str], env: Mapping[str, str]) -> Settings:
    path, data = load_profile(select_profile(profile, env), env)
    return validate([profile_layer(path, data), env_layer(env), override_layer(overrides)])


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


def restore_secrets(saved: Mapping[str, Any], current: Settings, overrides: list[str] | None = None) -> Settings:
    """Validate saved (redacted) settings, secrets taken from `current`, then `overrides` on top."""
    restored = unredact(saved, current)
    return validate([(restored, {}), override_layer(overrides or [])])


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

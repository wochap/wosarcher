from pathlib import Path

import pytest

from wosarcher.config import ConfigError, Settings, list_profiles, redact, resolve, store_profile


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {"XDG_CONFIG_HOME": str(tmp_path)}


def user_profile(env: dict[str, str], name: str, text: str) -> Path:
    path = Path(env["XDG_CONFIG_HOME"]) / "wosarcher" / "profiles" / f"{name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_defaults_validate() -> None:
    assert Settings().chunk.size == 1000


def test_invalid_release_names_allowed_values(env: dict[str, str]) -> None:
    user_profile(env, "bad", '[score]\nprovider = "rerank"\nrelease = "unload"\n')
    with pytest.raises(ConfigError) as error:
        resolve("bad", [], env)
    assert "score.release" in str(error.value)
    assert "'none', 'llama-swap' or 'ollama'" in str(error.value)


@pytest.mark.parametrize("name", ["low-vram", "workstation", "cloud"])
def test_builtin_profiles_validate(name: str, env: dict[str, str]) -> None:
    resolve(name, [], env)


def test_builtin_profile_used(env: dict[str, str]) -> None:
    assert resolve("cloud", [], env).score.provider == "jev"
    assert list_profiles(env)["cloud"][1] == "built-in"


def test_user_profile_overrides_builtin(env: dict[str, str]) -> None:
    user_profile(env, "cloud", '[score]\nprovider = "rerank"\nbase_url = "http://desktop.lan:8001"\n')
    settings = resolve("cloud", [], env)
    assert settings.score.base_url == "http://desktop.lan:8001"
    assert settings.llm.base_url == ""  # nothing from the built-in cloud profile
    assert list_profiles(env)["cloud"][1] == "user"


def test_unknown_profile_lists_available(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"nope.*cloud, low-vram, workstation"):
        resolve("nope", [], env)


def test_option_wins_over_environment(env: dict[str, str]) -> None:
    env["WOSARCHER_PROFILE"] = "cloud"
    assert resolve("low-vram", [], env).run.gpu_policy == "exclusive"


def test_stored_default(env: dict[str, str]) -> None:
    store_profile("cloud", env)
    assert resolve(None, [], env).score.provider == "jev"


def test_default_is_workstation(env: dict[str, str]) -> None:
    assert resolve(None, [], env).score.provider == "rerank"


def test_environment_overrides_profile(env: dict[str, str]) -> None:
    env["WOSARCHER_SCORE__PROVIDER"] = "jev"
    assert resolve("workstation", [], env).score.provider == "jev"


def test_override_wins_over_environment(env: dict[str, str]) -> None:
    env["WOSARCHER_SCORE__PROVIDER"] = "jev"
    assert resolve("workstation", ["score.provider=bm25"], env).score.provider == "bm25"


def test_unset_values_fall_back_to_defaults(env: dict[str, str]) -> None:
    assert resolve("workstation", [], env).chunk.size == 1000


def test_typed_override(env: dict[str, str]) -> None:
    assert resolve(None, ["score.top_k=12"], env).score.top_k == 12
    assert resolve(None, ["llm.fallback_urls=['http://b']"], env).llm.fallback_urls == ["http://b"]


def test_unknown_override_key(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"score\.topk.*--set score\.topk=12"):
        resolve(None, ["score.topk=12"], env)


def test_environment_value_typed_by_field(env: dict[str, str]) -> None:
    env["WOSARCHER_CHUNK__SIZE"] = "500"
    assert resolve(None, [], env).chunk.size == 500


def test_invalid_profile_value_names_file_and_field(env: dict[str, str]) -> None:
    path = user_profile(env, "bad", '[chunk]\nsize = "large"\n')
    with pytest.raises(ConfigError) as error:
        resolve("bad", [], env)
    assert "chunk.size" in str(error.value)
    assert str(path) in str(error.value)


def test_api_key_from_profile_is_redacted(env: dict[str, str]) -> None:
    user_profile(env, "keyed", '[score]\nprovider = "jev"\napi_key = "sk-secret"\n')
    settings = resolve("keyed", [], env)
    assert settings.score.api_key is not None
    assert settings.score.api_key.get_secret_value() == "sk-secret"
    shown = redact(settings)
    assert shown["score"]["api_key"] == "***"
    assert shown["llm"]["api_key"] == ""
    assert "sk-secret" not in str(shown)


def test_api_key_from_environment_is_redacted(env: dict[str, str]) -> None:
    env["WOSARCHER_SCORE__API_KEY"] = "sk-env"
    settings = resolve(None, [], env)
    assert settings.score.api_key is not None
    assert settings.score.api_key.get_secret_value() == "sk-env"
    assert redact(settings)["score"]["api_key"] == "***"


def test_time_range_invalid(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"search\.time_range"):
        resolve(None, ["search.time_range=decade"], env)


def test_page_timeout_must_be_below_timeout(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as error:
        resolve(None, ["fetch.page_timeout=60", "fetch.timeout=30"], env)
    assert "fetch.page_timeout" in str(error.value)
    assert "fetch.timeout" in str(error.value)


def test_fallback_rejects_remote_scorer(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as error:
        resolve(None, ["score.fallback=['rerank']"], env)
    assert "score.fallback" in str(error.value)
    assert "'bm25' or 'passthrough'" in str(error.value)


def test_ollama_release_needs_model(env: dict[str, str]) -> None:
    user_profile(env, "ollama", '[score]\nprovider = "rerank"\nrelease = "ollama"\n')
    with pytest.raises(ConfigError, match=r"score\.model"):
        resolve("ollama", [], env)


def test_collection_defaults() -> None:
    settings = Settings()
    assert (settings.plan.max_sub_queries, settings.attach.max_bytes) == (3, 5_000_000)
    assert (settings.chunk.size, settings.chunk.overlap) == (1000, 100)


def test_chunk_overlap_must_be_below_size(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"chunk\.overlap"):
        resolve(None, ["chunk.size=100", "chunk.overlap=100"], env)


def test_ranking_defaults() -> None:
    settings = Settings()
    assert (settings.prefilter.provider, settings.prefilter.top_k) == ("bm25", 50)
    assert (settings.score.min_score, settings.score.fallback) == (1.5, ["bm25", "passthrough"])
    select = settings.select
    assert (select.passthrough_chars, select.max_chunks_per_source, select.max_context_tokens) == (8000, 5, 16000)
    assert (select.file_share, select.prompt_reserve_tokens) == (0.5, 2000)
    llm = settings.llm
    assert (llm.context_window, llm.chars_per_token, llm.token_margin) == (32768, 3.5, 1.1)


def test_invalid_score_fallback_names_allowed_values(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as error:
        resolve("workstation", ['score.fallback=["jev"]'], env)
    assert "score.fallback" in str(error.value)
    assert "'bm25' or 'passthrough'" in str(error.value)


def test_file_share_above_one_fails(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"select\.file_share"):
        resolve("workstation", ["select.file_share=1.5"], env)


def test_server_defaults() -> None:
    server = Settings().server
    assert (server.host, server.port, server.max_concurrent_runs) == ("127.0.0.1", 8765, 1)
    assert server.static_dir == Path("web/dist")


def test_server_limit_from_environment(env: dict[str, str]) -> None:
    env["WOSARCHER_SERVER__MAX_CONCURRENT_RUNS"] = "2"
    assert resolve(None, [], env).server.max_concurrent_runs == 2


def test_auth_defaults() -> None:
    auth = Settings().auth
    assert (auth.password_hash, auth.session_days, auth.allowed_origins) == (None, 30, [])


def test_auth_password_hash_from_environment_is_redacted(env: dict[str, str]) -> None:
    env["WOSARCHER_AUTH__PASSWORD_HASH"] = "scrypt$15$8$1$salt$key"
    settings = resolve(None, [], env)
    assert settings.auth.password_hash is not None
    assert settings.auth.password_hash.get_secret_value() == "scrypt$15$8$1$salt$key"
    assert redact(settings)["auth"]["password_hash"] == "***"

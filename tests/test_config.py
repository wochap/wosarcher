from pathlib import Path

import pytest

from wosarcher.config import (
    ConfigError,
    Settings,
    list_profiles,
    load_depth,
    profile_description,
    redact,
    resolve,
    store_profile,
    to_toml,
)
from wosarcher.stages.select import output_tokens


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {"XDG_CONFIG_HOME": str(tmp_path)}


def user_profile(env: dict[str, str], name: str, text: str) -> Path:
    path = Path(env["XDG_CONFIG_HOME"]) / "wosarcher" / "profiles" / f"{name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_defaults_validate() -> None:
    assert Settings().chunk.size_chars == 1800


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
    assert resolve("workstation", [], env).chunk.size_chars == 1800


def test_typed_override(env: dict[str, str]) -> None:
    assert resolve(None, ["score.top_k=12"], env).score.top_k == 12
    assert resolve(None, ["llm.fallback_urls=['http://b']"], env).llm.fallback_urls == ["http://b"]


def test_unknown_override_key(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"score\.topk.*--set score\.topk=12"):
        resolve(None, ["score.topk=12"], env)


def test_environment_value_typed_by_field(env: dict[str, str]) -> None:
    env["WOSARCHER_CHUNK__SIZE_CHARS"] = "900"
    assert resolve(None, [], env).chunk.size_chars == 900


def test_invalid_profile_value_names_file_and_field(env: dict[str, str]) -> None:
    path = user_profile(env, "bad", '[chunk]\nsize_chars = "large"\n')
    with pytest.raises(ConfigError) as error:
        resolve("bad", [], env)
    assert "chunk.size_chars" in str(error.value)
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
    assert (settings.chunk.size_chars, settings.chunk.overlap, settings.chunk.min_chars) == (1800, 150, 500)


def test_chunk_overlap_must_be_below_size(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"chunk\.overlap"):
        resolve(None, ["chunk.size_chars=100", "chunk.overlap=100", "chunk.min_chars=50"], env)


def test_chunk_min_chars_must_be_below_size(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"chunk\.min_chars"):
        resolve(None, ["chunk.min_chars=2000"], env)


def test_old_chunk_size_key_fails(env: dict[str, str]) -> None:
    path = user_profile(env, "old", "[chunk]\nsize = 1000\n")
    with pytest.raises(ConfigError) as error:
        resolve("old", [], env)
    assert "chunk.size" in str(error.value)
    assert str(path) in str(error.value)


def test_ranking_defaults() -> None:
    settings = Settings()
    assert (settings.prefilter.provider, settings.prefilter.top_k) == ("bm25", 50)
    assert (settings.score.min_score, settings.score.fallback) == (1.5, ["bm25", "passthrough"])
    select = settings.select
    assert (select.passthrough_chars, select.max_chunks_per_source, select.max_context_tokens) == (8000, 5, "auto")
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
    assert (server.log_level, server.forwarded_allow_ips) == ("info", ["127.0.0.1"])


def test_server_log_level_from_environment(env: dict[str, str]) -> None:
    env["WOSARCHER_SERVER__LOG_LEVEL"] = "debug"
    assert resolve(None, [], env).server.log_level == "debug"


def test_server_log_level_invalid(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"server\.log_level"):
        resolve(None, ['server.log_level="loud"'], env)


def test_forwarded_allow_ips_from_environment(env: dict[str, str]) -> None:
    env["WOSARCHER_SERVER__FORWARDED_ALLOW_IPS"] = '["172.17.0.1"]'
    assert resolve(None, [], env).server.forwarded_allow_ips == ["172.17.0.1"]


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


def test_wire_format_defaults() -> None:
    settings = Settings()
    assert settings.llm.retry_budget == 60.0
    assert settings.llm.max_tokens_field == "max_completion_tokens"
    assert settings.llm.reasoning.model_dump() == {"plan": "none", "gap": "none", "write": "none"}
    assert settings.llm.max_continuations == 2
    assert settings.score.rerank_scale == "auto"
    assert settings.prefilter.pairing == "all"


def test_invalid_max_tokens_field(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as error:
        resolve("workstation", ['llm.max_tokens_field="n_predict"'], env)
    assert "llm.max_tokens_field" in str(error.value)
    assert "'max_completion_tokens' or 'max_tokens'" in str(error.value)


def test_negative_retry_budget_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"llm\.retry_budget"):
        resolve("workstation", ["llm.retry_budget=-1"], env)


def test_thinking_per_step(env: dict[str, str]) -> None:
    reasoning = resolve("workstation", ['llm.reasoning.write="high"'], env).llm.reasoning
    assert (reasoning.plan, reasoning.gap, reasoning.write) == ("none", "none", "high")


def test_invalid_thinking_level(env: dict[str, str]) -> None:
    user_profile(env, "bad", '[llm]\nprovider = "openai"\n[llm.reasoning]\ngap = "max"\n')
    with pytest.raises(ConfigError) as error:
        resolve("bad", [], env)
    assert "llm.reasoning.gap" in str(error.value)
    assert "'none', 'low', 'medium', 'high' or 'default'" in str(error.value)


def test_old_llm_provider(env: dict[str, str]) -> None:
    user_profile(env, "old", '[llm]\nprovider = "llm"\n')
    with pytest.raises(ConfigError) as error:
        resolve("old", [], env)
    assert "llm.provider" in str(error.value)
    assert "openai" in str(error.value)


def test_removed_reasoning_tokens(env: dict[str, str]) -> None:
    user_profile(env, "left", '[llm]\nprovider = "openai"\nreasoning_tokens = 4096\n')
    with pytest.raises(ConfigError, match=r"llm\.reasoning_tokens"):
        resolve("left", [], env)


def test_negative_continuations_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"llm\.max_continuations"):
        resolve("workstation", ["llm.max_continuations=-1"], env)


@pytest.mark.parametrize("name", ["workstation", "low-vram"])
def test_local_profiles_llm_timeout(name: str, env: dict[str, str]) -> None:
    assert resolve(name, [], env).llm.timeout == 600


def test_cloud_has_no_allowance(env: dict[str, str]) -> None:
    llm = resolve("cloud", [], env).llm
    assert (llm.provider, llm.reasoning.plan, llm.reasoning.gap, llm.reasoning.write) == ("openai", *["none"] * 3)
    assert "reasoning_tokens" not in llm.model_dump()


def test_description_is_not_a_setting(env: dict[str, str]) -> None:
    user_profile(env, "nixos", 'description = "x"\n[run]\ngpu_policy = "exclusive"\n')
    settings = resolve("nixos", [], env)
    assert settings.run.gpu_policy == "exclusive"
    assert "description" not in to_toml(redact(settings))
    assert profile_description("nixos", env) == "x"


def test_description_must_be_a_string(env: dict[str, str]) -> None:
    path = user_profile(env, "nixos", "description = 3\n")
    with pytest.raises(ConfigError, match=f"profile {path}: description must be a string"):
        profile_description("nixos", env)


def test_description_unset_is_empty(env: dict[str, str]) -> None:
    user_profile(env, "nixos", "[run]\n")
    assert profile_description("nixos", env) == ""


def test_builtin_descriptions(env: dict[str, str]) -> None:
    assert profile_description("workstation", env) == "One GPU fits all models; models stay loaded."
    assert profile_description("low-vram", env) == "Models take turns on one small GPU; slower, fits 8 GB."
    assert profile_description("cloud", env) == "Hosted APIs only; needs API keys."


PROVIDERS = '[search]\nprovider = "searxng"\n[fetch]\nprovider = "firecrawl"\n[score]\nprovider = "bm25"\n'


def test_auto_context_in_profile(env: dict[str, str]) -> None:
    user_profile(
        env,
        "big",
        PROVIDERS + '[llm]\nprovider = "openai"\ncontext_window = 1000000\n[select]\nmax_context_tokens = "auto"\n',
    )
    assert resolve("big", [], env).select.max_context_tokens == "auto"


def test_invalid_context_value(env: dict[str, str]) -> None:
    user_profile(env, "bad", PROVIDERS + '[llm]\nprovider = "openai"\n[select]\nmax_context_tokens = "all"\n')
    with pytest.raises(ConfigError, match=r"select\.max_context_tokens"):
        resolve("bad", [], env)


def test_fixed_context_cap(env: dict[str, str]) -> None:
    user_profile(env, "capped", PROVIDERS + '[llm]\nprovider = "openai"\n[select]\nmax_context_tokens = 12000\n')
    assert resolve("capped", [], env).select.max_context_tokens == 12000


def test_output_cap_default(env: dict[str, str]) -> None:
    settings = resolve(None, [], env, depth="exhaustive")
    assert settings.llm.max_output_tokens == 8192
    assert output_tokens(settings.write.words, settings.llm.max_output_tokens) == 6000


def test_larger_model_sets_its_own_cap(env: dict[str, str]) -> None:
    body = '[llm]\nprovider = "openai"\ncontext_window = 1048576\nmax_output_tokens = 131072\n'
    user_profile(env, "big", PROVIDERS + body)
    llm = resolve("big", [], env).llm
    assert (llm.context_window, llm.max_output_tokens) == (1048576, 131072)


def test_llm_timeout_default() -> None:
    settings = Settings()
    assert (settings.llm.timeout, settings.search.timeout) == (300, 60)


def test_gap_timeout_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env).run.stage_timeouts["gap"] == 360


def test_gap_context_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env).research.gap_context_tokens == 4000
    assert resolve(None, ["research.gap_context_tokens=auto"], env).research.gap_context_tokens == "auto"


def test_invalid_gap_context_value(env: dict[str, str]) -> None:
    user_profile(env, "bad", PROVIDERS + '[llm]\nprovider = "openai"\n[research]\ngap_context_tokens = "all"\n')
    with pytest.raises(ConfigError, match=r"research\.gap_context_tokens"):
        resolve("bad", [], env)


def test_page_cap_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env).fetch.max_pages == 40


def test_standard_equals_defaults(env: dict[str, str]) -> None:
    assert resolve(None, [], env, depth="standard") == resolve(None, [], env)


def test_deep_values(env: dict[str, str]) -> None:
    settings = resolve(None, [], env, depth="deep")
    assert (settings.plan.max_sub_queries, settings.fetch.max_pages, settings.write.words) == (6, 60, 2000)
    assert settings.select.max_context_tokens == "auto"
    assert (settings.research.rounds, settings.research.queries_per_round) == (3, 3)


def test_custom_applies_no_preset(env: dict[str, str]) -> None:
    assert resolve(None, [], env, depth="custom") == resolve(None, [], env)


def test_unknown_depth_lists_presets(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match="quick, standard, deep, exhaustive"):
        resolve(None, [], env, depth="huge")


def test_provider_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "odd.toml"
    path.write_text('[llm]\nmodel = "x"\n')
    with pytest.raises(ConfigError) as error:
        load_depth("odd", tmp_path)
    assert str(path) in str(error.value)
    assert "llm.model" in str(error.value)


def test_rounds_above_eight_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"research\.rounds"):
        resolve(None, ["research.rounds=9"], env)


def test_preset_beats_environment(env: dict[str, str]) -> None:
    env["WOSARCHER_PLAN__MAX_SUB_QUERIES"] = "4"
    assert resolve(None, [], env, depth="quick").plan.max_sub_queries == 3


def test_flag_beats_preset(env: dict[str, str]) -> None:
    settings = resolve(None, ["write.words=800"], env, depth="deep")
    assert (settings.write.words, settings.plan.max_sub_queries) == (800, 6)


def test_preset_between_environment_and_overrides(env: dict[str, str]) -> None:
    user_profile(env, "mid", PROVIDERS + '[llm]\nprovider = "openai"\n' + "[plan]\nmax_sub_queries = 1\n")
    assert resolve("mid", [], env, depth="deep").plan.max_sub_queries == 6
    overrides = ["plan.max_sub_queries=2"]
    assert resolve("mid", overrides, env, depth="deep").plan.max_sub_queries == 2


def test_domain_entries_normalised(env: dict[str, str]) -> None:
    user_profile(env, "p", '[search]\nprovider = "searxng"\nallow_domains = ["*.GOB.pe", "gob.pe", "sbs.gob.pe"]\n')
    assert resolve("p", [], env).search.allow_domains == ["gob.pe", "sbs.gob.pe"]


def test_domain_url_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as error:
        resolve(None, ['search.block_domains=["https://facebook.com/"]'], env)
    assert "search.block_domains" in str(error.value)
    assert "https://facebook.com/" in str(error.value)


def test_domain_defaults(env: dict[str, str]) -> None:
    search = resolve(None, [], env).search
    assert search.allow_domains == []
    assert search.block_domains == []
    assert search.filter_pages == 3


def test_preset_cannot_set_domains(tmp_path: Path) -> None:
    (tmp_path / "narrow.toml").write_text('[search]\nallow_domains = ["gob.pe"]\n')
    with pytest.raises(ConfigError, match=r"search\.allow_domains"):
        load_depth("narrow", tmp_path)


def test_invalid_prefilter_pairing(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as error:
        resolve("workstation", ['prefilter.pairing="some"'], env)
    assert "prefilter.pairing" in str(error.value)
    assert "'all' or 'found'" in str(error.value)

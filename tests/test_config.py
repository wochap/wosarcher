import tomllib
from pathlib import Path

import pytest
from pydantic import SecretStr

from wosarcher.config import (
    CatalogConfig,
    ConfigError,
    Settings,
    catalog_structure,
    fork_settings,
    list_depths,
    list_entries,
    list_profiles,
    load_depth,
    prune_unknown,
    read_entry,
    read_profile,
    redact,
    resolve,
    resolve_run,
    store_profile,
    to_toml,
)
from wosarcher.stages.select import output_tokens

BASE_PROFILE = '[use]\nprefilter = "bm25"\n'


def write(env: dict[str, str], relative: str, text: str) -> Path:
    path = Path(env["XDG_CONFIG_HOME"]) / "wosarcher" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def user_profile(env: dict[str, str], name: str, text: str) -> Path:
    return write(env, f"profiles/{name}.toml", text)


def entry(env: dict[str, str], block: str, name: str, text: str) -> Path:
    return write(env, f"providers/{block}/{name}.toml", text)


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """One entry per block (prefilter chosen by the profile `p`), and the profile `p`."""
    env = {"XDG_CONFIG_HOME": str(tmp_path / "config")}
    entry(env, "search", "searxng", 'provider = "searxng"\nbase_url = "http://searx.test"\n')
    entry(env, "fetch", "firecrawl", 'provider = "firecrawl"\nbase_url = "http://crawl.test/v1"\n')
    entry(env, "llm", "agents", 'provider = "openai"\nbase_url = "http://llm.test/v1"\nmodel = "qwen3-14b"\n')
    user_profile(env, "p", BASE_PROFILE)
    return env


def test_defaults_validate() -> None:
    assert Settings().chunk.size_chars == 1800


# Entry files


def test_scorer_entry(env: dict[str, str]) -> None:
    entry(
        env, "score", "jev-strict", 'provider = "jev"\nbase_url = "http://jev.test"\napi_key = "k"\nmin_score = 2.5\n'
    )
    user_profile(env, "p", BASE_PROFILE + 'score = "jev-strict"\n')
    score = resolve(None, [], env).score
    assert (score.provider, score.base_url, score.min_score, score.top_k) == ("jev", "http://jev.test", 2.5, 10)


def test_same_provider_in_two_blocks(env: dict[str, str]) -> None:
    entry(env, "prefilter", "kw", 'provider = "bm25"\n')
    entry(env, "score", "kw", 'provider = "bm25"\n')
    entries = list_entries(env)
    assert "kw" in entries["prefilter"]
    assert "kw" in entries["score"]


def test_unknown_block_directory(env: dict[str, str]) -> None:
    entry(env, "scorer", "x", 'provider = "bm25"\n')
    with pytest.raises(ConfigError, match=r"providers/scorer.*search, fetch, prefilter, score, llm"):
        resolve(None, [], env)


def test_invalid_entry_value_names_file(env: dict[str, str]) -> None:
    path = entry(env, "score", "rr", 'provider = "rerank"\nbase_url = "http://rr.test"\nrelease = "unload"\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, ["use.score=rr"], env)
    assert "score.release" in str(error.value)
    assert str(path) in str(error.value)
    assert "'none', 'llama-swap' or 'ollama'" in str(error.value)


def test_invalid_entry_type_names_file(env: dict[str, str]) -> None:
    path = entry(env, "fetch", "firecrawl", 'provider = "firecrawl"\nmax_chars = "lots"\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, [], env)
    assert "fetch.max_chars" in str(error.value)
    assert str(path) in str(error.value)


# Built-in entries


def test_builtin_entries(tmp_path: Path) -> None:
    entries = list_entries({"XDG_CONFIG_HOME": str(tmp_path)})
    assert list(entries["prefilter"]) == ["bm25", "none"]
    assert list(entries["score"]) == ["bm25"]
    assert {e.source for block in ("prefilter", "score") for e in entries[block].values()} == {"builtin"}


def test_user_file_replaces_builtin(env: dict[str, str]) -> None:
    entry(env, "score", "bm25", 'provider = "bm25"\ncandidates = 80\n')
    assert list_entries(env)["score"]["bm25"].source == "user"
    assert resolve(None, [], env).score.candidates == 80


# Keys an entry may set


def test_depth_key_in_entry(env: dict[str, str]) -> None:
    path = entry(env, "score", "jev-wide", 'provider = "jev"\ntop_k = 25\n')
    with pytest.raises(ConfigError, match=rf"{path}: top_k .*depth presets own"):
        read_entry(list_entries(env)["score"]["jev-wide"])


def test_domain_list_in_entry(env: dict[str, str]) -> None:
    path = entry(env, "search", "searxng", 'provider = "searxng"\nblock_domains = ["facebook.com"]\n')
    with pytest.raises(ConfigError, match=rf"{path}: block_domains .*profiles own"):
        resolve(None, [], env)


def test_model_key_at_entry_top(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", 'provider = "openai"\ncontext_window = 1000\n')
    with pytest.raises(ConfigError, match=r"context_window .*the model owns"):
        resolve(None, [], env)


def test_secret_from_file(env: dict[str, str], tmp_path: Path) -> None:
    secret = tmp_path / "omniroute"
    secret.write_text("sk-live\n")
    entry(env, "llm", "agents", f'provider = "openai"\napi_key_file = "{secret}"\n')
    settings = resolve(None, [], env)
    assert settings.llm.api_key == SecretStr("sk-live")
    assert redact(settings)["llm"]["api_key"] == "***"
    assert redact(settings)["llm"]["api_key_file"] == str(secret)


def test_old_prefilter_key(env: dict[str, str]) -> None:
    path = entry(env, "prefilter", "kw", 'provider = "bm25"\ntop_k = 100\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, ["use.prefilter=kw"], env)
    assert "prefilter.top_k" in str(error.value)
    assert str(path) in str(error.value)


def test_old_prefilter_override_fails(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"prefilter\.top_k"):
        resolve(None, ["prefilter.top_k=5"], env)


def test_candidates_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env).score.candidates == 50


# LLM entries and models

OMNIROUTE = """provider = "openai"
base_url = "http://ssc:20700/v1"
model = "research-smart"

[models.research-smart]
context_window = 1048576
max_output_tokens = 131072
gap_context_tokens = "auto"
reasoning = { write = "low" }

[models.research-fast]
context_window = 131072
"""


def test_listed_model(env: dict[str, str]) -> None:
    entry(env, "llm", "omniroute", OMNIROUTE)
    settings = resolve(None, ["use.llm=omniroute"], env)
    llm = settings.llm
    assert (llm.model, llm.context_window, llm.max_output_tokens) == ("research-smart", 1048576, 131072)
    assert (llm.reasoning.write, llm.reasoning.plan) == ("low", "none")
    assert settings.research.gap_context_tokens == "auto"


def test_unlisted_model(env: dict[str, str]) -> None:
    entry(env, "llm", "omniroute", OMNIROUTE)
    settings = resolve(None, ["use.llm=omniroute", 'llm.model="qwen3-30b-a3b"'], env)
    assert (settings.llm.context_window, settings.llm.max_output_tokens) == (32768, 8192)
    assert settings.llm.reasoning.model_dump() == {
        "plan": "none",
        "gap": "none",
        "write": "none",
        "draft": "none",
        "extract": "none",
    }
    assert settings.research.gap_context_tokens == 4000


def test_run_overrides_model_limit(env: dict[str, str]) -> None:
    overrides = ['llm.model="qwen3-30b-a3b"', "llm.context_window=262144"]
    llm = resolve(None, overrides, env).llm
    assert (llm.context_window, llm.max_output_tokens) == (262144, 8192)


def test_catalog_steps_for_a_model(env: dict[str, str]) -> None:
    body = 'provider = "openai"\nmodel = "m"\n[models.m]\nreasoning = { extract = "low", draft = "high" }\n'
    entry(env, "llm", "agents", body)
    reasoning = resolve(None, [], env).llm.reasoning
    assert (reasoning.extract, reasoning.draft, reasoning.plan, reasoning.gap, reasoning.write) == (
        "low",
        "high",
        "none",
        "none",
        "none",
    )


def test_unknown_reasoning_step(env: dict[str, str]) -> None:
    path = entry(env, "llm", "agents", 'provider = "openai"\nmodel = "m"\n[models.m]\nreasoning = { crawl = "low" }\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, [], env)
    assert str(path) in str(error.value)
    assert "crawl" in str(error.value)


def test_unknown_model_key(env: dict[str, str]) -> None:
    path = entry(env, "llm", "omniroute", OMNIROUTE + "timeout = 900\n")
    with pytest.raises(ConfigError, match=rf"{path}: models.research-fast: timeout"):
        resolve(None, ["use.llm=omniroute"], env)


def test_invalid_model_thinking(env: dict[str, str]) -> None:
    path = entry(env, "llm", "agents", 'provider = "openai"\nmodel = "m"\n[models.m]\nreasoning = { gap = "max" }\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, [], env)
    assert "llm.reasoning.gap" in str(error.value)
    assert f"{path} models.m" in str(error.value)
    assert "'none', 'low', 'medium', 'high' or 'default'" in str(error.value)


def test_models_only_in_llm_entries(env: dict[str, str]) -> None:
    entry(env, "score", "rr", 'provider = "rerank"\n[models.x]\ncontext_window = 1\n')
    with pytest.raises(ConfigError, match="only llm entries list models"):
        resolve(None, ["use.score=rr"], env)


# Entry selection


def test_profile_choice(env: dict[str, str]) -> None:
    entry(env, "score", "rerank", 'provider = "rerank"\nbase_url = "http://rr.test"\n')
    entry(env, "llm", "omniroute", OMNIROUTE)
    user_profile(env, "p", BASE_PROFILE + 'score = "rerank"\nllm = "omniroute"\n')
    resolved = resolve_run(None, [], env)
    assert (resolved.settings.score.provider, resolved.settings.llm.base_url) == ("rerank", "http://ssc:20700/v1")
    assert resolved.use == {
        "search": "searxng",
        "fetch": "firecrawl",
        "prefilter": "bm25",
        "score": "rerank",
        "llm": "omniroute",
    }


def test_run_choice_wins(env: dict[str, str]) -> None:
    entry(env, "score", "rerank", 'provider = "rerank"\nbase_url = "http://rr.test"\n')
    entry(env, "score", "jev-strict", 'provider = "jev"\nbase_url = "http://jev.test"\n')
    user_profile(env, "p", BASE_PROFILE + 'score = "rerank"\n')
    env["WOSARCHER_USE__SCORE"] = "bm25"
    assert resolve(None, [], env).score.provider == "bm25"
    assert resolve(None, ["use.score=jev-strict"], env).score.provider == "jev"


def test_single_entry_implied(env: dict[str, str]) -> None:
    assert resolve_run(None, [], env).use["search"] == "searxng"


def test_ambiguous_block(env: dict[str, str]) -> None:
    entry(env, "score", "rerank", 'provider = "rerank"\n')
    with pytest.raises(ConfigError, match=r"score entry.*score entries: bm25, rerank"):
        resolve(None, [], env)


def test_unknown_entry(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"unknown llm entry 'sonet'; llm entries: agents"):
        resolve(None, ["use.llm=sonet"], env)


def test_unknown_block_in_use(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"use\.scorer is not a block"):
        resolve(None, ["use.scorer=bm25"], env)


# Keys a profile may set


def test_provider_key_in_profile(env: dict[str, str]) -> None:
    path = user_profile(env, "p", BASE_PROFILE + '[score]\nbase_url = "http://desktop.lan:8001/v1"\n')
    with pytest.raises(ConfigError, match=rf"{path}: score.base_url .*provider entries own"):
        resolve(None, [], env)


def test_model_key_in_profile(env: dict[str, str]) -> None:
    path = user_profile(env, "p", BASE_PROFILE + '[llm.reasoning]\nwrite = "high"\n')
    with pytest.raises(ConfigError, match=rf"{path}: llm.reasoning.write .*the model owns"):
        resolve(None, [], env)


def test_model_table_in_profile(env: dict[str, str]) -> None:
    table = '[models."claude-sonnet-5-5"]\ncontext_window = 200000\nreasoning = { write = "high" }\n'
    user_profile(env, "p", BASE_PROFILE + table)
    profile = read_profile("p", env)
    assert profile.models == {"claude-sonnet-5-5": {"context_window": 200000, "reasoning": {"write": "high"}}}
    resolve(None, [], env)


def test_unknown_key_in_profile_model_table(env: dict[str, str]) -> None:
    path = user_profile(env, "p", BASE_PROFILE + "[models.research-smart]\ntimeout = 900\n")
    with pytest.raises(ConfigError, match=rf"profile {path}: models.research-smart: timeout"):
        resolve(None, [], env)


def test_depth_key_in_profile(env: dict[str, str]) -> None:
    user_profile(env, "p", BASE_PROFILE + "[plan]\nmax_sub_queries = 1\n")
    with pytest.raises(ConfigError, match=r"plan.max_sub_queries .*depth presets own"):
        resolve(None, [], env)


def test_environment_cannot_set_block_key(env: dict[str, str]) -> None:
    env["WOSARCHER_SCORE__PROVIDER"] = "jev"
    with pytest.raises(ConfigError, match=r"WOSARCHER_SCORE__PROVIDER: score.provider .*provider entries own"):
        resolve(None, [], env)


def test_set_reaches_any_key(env: dict[str, str]) -> None:
    assert resolve(None, ["score.min_score=1.5"], env).score.min_score == 1.5


def test_profile_owned_block_keys(env: dict[str, str]) -> None:
    profile = (
        BASE_PROFILE + '[llm]\nmodel = "other"\n[search]\nlanguage = "es"\nallow_domains = ["*.GOB.pe", "gob.pe"]\n'
    )
    user_profile(env, "p", profile)
    settings = resolve(None, [], env)
    assert (settings.llm.model, settings.search.language, settings.search.allow_domains) == ("other", "es", ["gob.pe"])


# Profiles and profile selection


def test_no_builtin_profiles(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    assert list_profiles(env) == {}
    with pytest.raises(ConfigError, match=rf"no profiles; add one in {tmp_path / 'wosarcher' / 'profiles'}"):
        resolve(None, [], env)


def test_unknown_profile_lists_available(env: dict[str, str]) -> None:
    user_profile(env, "q", BASE_PROFILE)
    with pytest.raises(ConfigError, match=r"nope.*p, q"):
        resolve("nope", [], env)


def test_option_wins_over_environment(env: dict[str, str]) -> None:
    user_profile(env, "x", BASE_PROFILE + '[run]\ngpu_policy = "exclusive"\n')
    env["WOSARCHER_PROFILE"] = "p"
    assert resolve("x", [], env).run.gpu_policy == "exclusive"


def test_stored_default(env: dict[str, str]) -> None:
    user_profile(env, "x", BASE_PROFILE + '[run]\ngpu_policy = "exclusive"\n')
    store_profile("x", env)
    assert resolve(None, [], env).run.gpu_policy == "exclusive"


def test_first_profile_by_name(env: dict[str, str]) -> None:
    user_profile(env, "cloud", BASE_PROFILE + '[run]\ngpu_policy = "exclusive"\n')
    assert resolve(None, [], env).run.gpu_policy == "exclusive"


def test_description_is_not_a_setting(env: dict[str, str]) -> None:
    user_profile(env, "p", 'description = "x"\n' + BASE_PROFILE + '[run]\ngpu_policy = "exclusive"\n')
    settings = resolve(None, [], env)
    assert settings.run.gpu_policy == "exclusive"
    assert "description" not in to_toml(redact(settings))
    assert read_profile("p", env).description == "x"


def test_description_must_be_a_string(env: dict[str, str]) -> None:
    path = user_profile(env, "p", "description = 3\n")
    with pytest.raises(ConfigError, match=f"profile {path}: description must be a string"):
        read_profile("p", env)


def test_description_unset_is_empty(env: dict[str, str]) -> None:
    assert read_profile("p", env).description == ""


def test_local_llm_timeout(env: dict[str, str]) -> None:
    assert resolve(None, [], env).llm.timeout == 300
    entry(env, "llm", "agents", 'provider = "openai"\ntimeout = 600\n')
    assert resolve(None, [], env).llm.timeout == 600


def test_no_reasoning_allowance(env: dict[str, str]) -> None:
    llm = resolve(None, [], env).llm
    assert (llm.reasoning.plan, llm.reasoning.gap, llm.reasoning.write) == ("none", "none", "none")
    assert "reasoning_tokens" not in llm.model_dump()


# Precedence


def test_profile_over_entry(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", OMNIROUTE)
    user_profile(env, "p", BASE_PROFILE + '[llm]\nmodel = "research-fast"\n')
    llm = resolve(None, [], env).llm
    assert (llm.model, llm.context_window) == ("research-fast", 131072)


def test_profile_model_table_over_entry_model_table(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", OMNIROUTE)
    user_profile(env, "p", BASE_PROFILE + '[models.research-smart]\nreasoning = { write = "high" }\n')
    llm = resolve(None, [], env).llm
    assert (llm.reasoning.write, llm.max_output_tokens) == ("high", 131072)


def test_profile_model_table_for_another_model(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", OMNIROUTE)
    user_profile(env, "p", BASE_PROFILE + "[models.research-smart]\ncontext_window = 200000\n")
    llm = resolve(None, ['llm.model="research-fast"'], env).llm
    assert llm.context_window == 131072


def test_run_edit_over_profile_model_table(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", OMNIROUTE)
    user_profile(env, "p", BASE_PROFILE + "[models.research-smart]\ncontext_window = 200000\n")
    assert resolve(None, ["llm.context_window=100000"], env).llm.context_window == 100000


def test_environment_overrides_profile(env: dict[str, str]) -> None:
    user_profile(env, "p", BASE_PROFILE + "[select]\nmax_context_tokens = 12000\n")
    env["WOSARCHER_SELECT__MAX_CONTEXT_TOKENS"] = "auto"
    assert resolve(None, [], env).select.max_context_tokens == "auto"


def test_override_flag_wins(env: dict[str, str]) -> None:
    entry(env, "score", "bm25", 'provider = "bm25"\nmin_score = 2.0\n')
    assert resolve(None, ["score.min_score=1.0"], env).score.min_score == 1.0


def test_unset_values_fall_back_to_defaults(env: dict[str, str]) -> None:
    assert resolve(None, [], env).chunk.size_chars == 1800


def test_model_override_picks_model_values(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", OMNIROUTE)
    assert resolve(None, ['llm.model="research-fast"'], env).llm.context_window == 131072


def test_preset_between_environment_and_overrides(env: dict[str, str]) -> None:
    assert resolve(None, [], env, depth="deep").fetch.max_pages == 60
    assert resolve(None, ["fetch.max_pages=80"], env, depth="deep").fetch.max_pages == 80


def test_typed_override(env: dict[str, str]) -> None:
    assert resolve(None, ["score.top_k=12"], env).score.top_k == 12
    assert resolve(None, ["llm.fallback_urls=['http://b']"], env).llm.fallback_urls == ["http://b"]


def test_environment_value_typed_by_field(env: dict[str, str]) -> None:
    env["WOSARCHER_CHUNK__SIZE_CHARS"] = "900"
    assert resolve(None, [], env).chunk.size_chars == 900


# Validation


def test_unknown_override_key(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"score\.topk.*--set score\.topk=12"):
        resolve(None, ["score.topk=12"], env)


def test_invalid_profile_value_names_file_and_field(env: dict[str, str]) -> None:
    path = user_profile(env, "p", BASE_PROFILE + '[chunk]\nsize_chars = "large"\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, [], env)
    assert "chunk.size_chars" in str(error.value)
    assert str(path) in str(error.value)


def test_old_chunk_size_key_fails(env: dict[str, str]) -> None:
    path = user_profile(env, "p", BASE_PROFILE + "[chunk]\nsize = 1000\n")
    with pytest.raises(ConfigError) as error:
        resolve(None, [], env)
    assert "chunk.size" in str(error.value)
    assert str(path) in str(error.value)


def test_chunk_overlap_must_be_below_size(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"chunk\.overlap"):
        resolve(None, ["chunk.size_chars=100", "chunk.overlap=100", "chunk.min_chars=50"], env)


def test_chunk_min_chars_must_be_below_size(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"chunk\.min_chars"):
        resolve(None, ["chunk.min_chars=2000"], env)


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
    entry(env, "score", "rr", 'provider = "rerank"\nrelease = "ollama"\n')
    with pytest.raises(ConfigError, match=r"score\.model"):
        resolve(None, ["use.score=rr"], env)


def test_file_share_above_one_fails(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"select\.file_share"):
        resolve(None, ["select.file_share=1.5"], env)


def test_invalid_max_tokens_field(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", 'provider = "openai"\nmax_tokens_field = "n_predict"\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, [], env)
    assert "llm.max_tokens_field" in str(error.value)
    assert "'max_completion_tokens' or 'max_tokens'" in str(error.value)


def test_negative_retry_budget_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"llm\.retry_budget"):
        resolve(None, ["llm.retry_budget=-1"], env)


def test_thinking_per_step(env: dict[str, str]) -> None:
    reasoning = resolve(None, ['llm.reasoning.write="high"'], env).llm.reasoning
    assert (reasoning.plan, reasoning.gap, reasoning.write) == ("none", "none", "high")


def test_old_llm_provider(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", 'provider = "llm"\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, [], env)
    assert "llm.provider" in str(error.value)
    assert "openai" in str(error.value)


def test_removed_reasoning_tokens(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", 'provider = "openai"\nreasoning_tokens = 4096\n')
    with pytest.raises(ConfigError, match=r"llm\.reasoning_tokens"):
        resolve(None, [], env)


def test_negative_continuations_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"llm\.max_continuations"):
        resolve(None, ["llm.max_continuations=-1"], env)


def test_prefilter_pairing_is_unknown(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"prefilter\.pairing"):
        resolve(None, ['prefilter.pairing="found"'], env)


def test_invalid_prefilter_context_names_allowed_values(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as error:
        resolve(None, ['prefilter.context="title"'], env)
    assert "prefilter.context" in str(error.value)
    assert "'header' or 'body'" in str(error.value)


def test_rounds_above_eight_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"research\.rounds"):
        resolve(None, ["research.rounds=9"], env)


# Defaults


def test_collection_defaults() -> None:
    settings = Settings()
    assert (settings.plan.max_sub_queries, settings.attach.max_bytes) == (3, 5_000_000)
    assert (settings.chunk.size_chars, settings.chunk.overlap, settings.chunk.min_chars) == (1800, 150, 500)


def test_ranking_defaults() -> None:
    settings = Settings()
    assert (settings.prefilter.provider, settings.score.candidates) == ("bm25", 50)
    assert (settings.score.min_score, settings.score.fallback) == (2.0, ["bm25", "passthrough"])
    select = settings.select
    assert (select.passthrough_chars, select.max_chunks_per_source, select.max_context_tokens) == (8000, 5, "auto")
    assert (select.file_share, select.prompt_reserve_tokens) == (0.5, 2000)
    llm = settings.llm
    assert (llm.context_window, llm.chars_per_token, llm.token_margin) == (32768, 3.5, 1.1)


def test_server_defaults() -> None:
    server = Settings().server
    assert (server.host, server.port) == ("127.0.0.1", 8765)
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


def test_server_limit_removed(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"server\.max_concurrent_runs"):
        resolve(None, ["server.max_concurrent_runs=2"], env)


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
    assert settings.llm.reasoning.model_dump() == {
        "plan": "none",
        "gap": "none",
        "write": "none",
        "draft": "none",
        "extract": "none",
    }
    assert settings.llm.max_continuations == 2
    assert settings.score.rerank_scale == "auto"


def test_llm_timeout_default() -> None:
    settings = Settings()
    assert (settings.llm.timeout, settings.search.timeout) == (300, 60)


def test_gap_timeout_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env).run.stage_timeouts["gap"] == 360


def test_gap_context_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env).research.gap_context_tokens == 4000
    assert resolve(None, ["research.gap_context_tokens=auto"], env).research.gap_context_tokens == "auto"


def test_gap_parts_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env).research.gap_parts is True
    assert resolve(None, ["research.gap_parts=false"], env).research.gap_parts is False


def test_invalid_gap_parts_value(env: dict[str, str]) -> None:
    user_profile(env, "p", BASE_PROFILE + '[research]\ngap_parts = "yes"\n')
    with pytest.raises(ConfigError, match=r"research\.gap_parts"):
        resolve(None, [], env)


def test_domain_url_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as error:
        resolve(None, ['search.block_domains=["https://facebook.com/"]'], env)
    assert "search.block_domains" in str(error.value)
    assert "https://facebook.com/" in str(error.value)


def test_domain_defaults(env: dict[str, str]) -> None:
    search = resolve(None, [], env).search
    assert (search.allow_domains, search.block_domains, search.filter_pages) == ([], [], 3)


# Output and context sizing


def test_auto_context_in_profile(env: dict[str, str]) -> None:
    user_profile(env, "p", BASE_PROFILE + '[select]\nmax_context_tokens = "auto"\n')
    assert resolve(None, [], env).select.max_context_tokens == "auto"


def test_invalid_context_value(env: dict[str, str]) -> None:
    user_profile(env, "p", BASE_PROFILE + '[select]\nmax_context_tokens = "all"\n')
    with pytest.raises(ConfigError, match=r"select\.max_context_tokens"):
        resolve(None, [], env)


def test_fixed_context_cap(env: dict[str, str]) -> None:
    user_profile(env, "p", BASE_PROFILE + "[select]\nmax_context_tokens = 12000\n")
    assert resolve(None, [], env).select.max_context_tokens == 12000


def test_output_cap_default(env: dict[str, str]) -> None:
    settings = resolve(None, [], env, depth="exhaustive")
    assert settings.llm.max_output_tokens == 8192
    assert output_tokens(settings.write.words, settings.llm.max_output_tokens) == 6000


def test_larger_model_sets_its_own_cap(env: dict[str, str]) -> None:
    entry(env, "llm", "agents", OMNIROUTE)
    llm = resolve(None, [], env).llm
    assert (llm.context_window, llm.max_output_tokens) == (1048576, 131072)


def test_page_cap_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env).fetch.max_pages == 40


# Depth presets


def test_standard_equals_defaults(env: dict[str, str]) -> None:
    assert resolve(None, [], env, depth="standard") == resolve(None, [], env)


def test_deep_values(env: dict[str, str]) -> None:
    user_profile(env, "p", BASE_PROFILE + "[select]\nmax_context_tokens = 12000\n")
    settings = resolve(None, [], env, depth="deep")
    assert (settings.plan.max_sub_queries, settings.fetch.max_pages, settings.write.words) == (6, 60, 2000)
    assert settings.select.max_context_tokens == 12000
    assert (settings.research.rounds, settings.research.queries_per_round) == (3, 3)


def test_custom_applies_no_preset(env: dict[str, str]) -> None:
    assert resolve(None, [], env, depth="custom") == resolve(None, [], env)


def test_unknown_depth_lists_presets(env: dict[str, str]) -> None:
    write(env, "depths/wide.toml", "[plan]\nmax_sub_queries = 10\n")
    with pytest.raises(ConfigError, match="quick, standard, deep, exhaustive, wide"):
        resolve(None, [], env, depth="huge")


def test_user_preset_listed_and_used(env: dict[str, str]) -> None:
    write(env, "depths/wide.toml", 'description = "Broad survey."\n[plan]\nmax_sub_queries = 10\n[score]\ntop_k = 25\n')
    found = list_depths(env)
    assert list(found) == ["quick", "standard", "deep", "exhaustive", "wide"]
    assert (found["wide"].source, found["deep"].source) == ("user", "builtin")
    settings = resolve(None, [], env, depth="wide")
    assert (settings.plan.max_sub_queries, settings.score.top_k) == (10, 25)


def test_user_preset_built_in_name(env: dict[str, str]) -> None:
    path = write(env, "depths/deep.toml", "[plan]\nmax_sub_queries = 10\n")
    with pytest.raises(ConfigError, match=rf"{path}: deep"):
        list_depths(env)


def test_preset_provider_key_rejected(env: dict[str, str]) -> None:
    path = write(env, "depths/odd.toml", '[llm]\nmodel = "x"\n')
    with pytest.raises(ConfigError) as error:
        load_depth("odd", env)
    assert str(path) in str(error.value)
    assert "llm.model" in str(error.value)


@pytest.mark.parametrize("key", ["select.max_context_tokens", "research.gap_context_tokens"])
def test_preset_context_budget_rejected(env: dict[str, str], key: str) -> None:
    block, field = key.split(".")
    write(env, "depths/odd.toml", f"[{block}]\n{field} = 20000\n")
    with pytest.raises(ConfigError, match=key.replace(".", r"\.")):
        load_depth("odd", env)


def test_preset_cannot_set_domains(env: dict[str, str]) -> None:
    write(env, "depths/narrow.toml", '[search]\nallow_domains = ["gob.pe"]\n')
    with pytest.raises(ConfigError, match=r"search\.allow_domains"):
        load_depth("narrow", env)


def test_preset_key_in_environment_fails(env: dict[str, str]) -> None:
    env["WOSARCHER_PLAN__MAX_SUB_QUERIES"] = "4"
    with pytest.raises(ConfigError, match=r"WOSARCHER_PLAN__MAX_SUB_QUERIES: .*depth presets own"):
        resolve(None, [], env, depth="quick")


def test_flag_beats_preset(env: dict[str, str]) -> None:
    settings = resolve(None, ["write.words=800"], env, depth="deep")
    assert (settings.write.words, settings.plan.max_sub_queries) == (800, 6)


def test_preset_beats_default(env: dict[str, str]) -> None:
    assert resolve(None, [], env, depth="quick").plan.max_sub_queries == 3


# Secret sources


def test_two_secret_forms_fail(env: dict[str, str], tmp_path: Path) -> None:
    entry(env, "llm", "agents", 'provider = "openai"\napi_key = "x"\n')
    with pytest.raises(ConfigError) as error:
        resolve(None, [f"llm.api_key_file={tmp_path / 'k'}"], env)
    assert "api_key, api_key_file, api_key_command" in str(error.value)


def test_key_from_command(env: dict[str, str]) -> None:
    entry(env, "score", "jev", 'provider = "jev"\napi_key_command = ["sh", "-c", "printf \'tk-1\\\\n\'"]\n')
    assert resolve(None, ["use.score=jev"], env).score.api_key == SecretStr("tk-1")


def test_password_hash_from_command(env: dict[str, str]) -> None:
    settings = resolve(None, ['auth.password_hash_command=["printf", "scrypt$x\\n"]'], env)
    assert settings.auth.password_hash == SecretStr("scrypt$x")


def test_missing_key_file(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"llm\.api_key_file.*/run/secrets/missing"):
        resolve(None, ["llm.api_key_file=/run/secrets/missing"], env)


def test_failing_command(env: dict[str, str]) -> None:
    command = 'score.api_key_command=["sh", "-c", "echo leaked; exit 3"]'
    with pytest.raises(ConfigError) as error:
        resolve(None, [command], env)
    assert "score.api_key_command: sh exited with status 3" in str(error.value)
    assert "leaked" not in str(error.value)


def test_false_command(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match=r"score\.api_key_command: false exited with status 1"):
        resolve(None, ['score.api_key_command=["false"]'], env)


def test_non_utf8_command(env: dict[str, str]) -> None:
    command = 'llm.api_key_command=["sh", "-c", "printf \'\\\\377\'"]'
    with pytest.raises(ConfigError, match=r"llm\.api_key_command: sh printed output that is not UTF-8"):
        resolve(None, [command], env)


# Forks


def test_fork_drops_unknown_keys(env: dict[str, str]) -> None:
    current = resolve_run(None, [], env)
    saved = redact(current.settings)
    saved["llm"]["reasoning_tokens"] = 4096
    saved["prefilter"]["top_k"] = 50
    resolved, dropped = fork_settings(saved, current.use, {}, [], env)
    assert sorted(dropped) == ["llm.reasoning_tokens", "prefilter.top_k"]
    assert resolved.settings.llm == current.settings.llm


def test_prune_keeps_dict_field_keys() -> None:
    saved = {"run": {"stage_timeouts": {"nope": 1}}}
    assert prune_unknown(saved, Settings) == (saved, [])


def test_fork_rejects_bad_value(env: dict[str, str]) -> None:
    current = resolve_run(None, [], env)
    saved = redact(current.settings)
    saved["llm"]["provider"] = "llm"
    with pytest.raises(ConfigError, match=r"llm\.provider"):
        fork_settings(saved, current.use, {}, [], env)


def test_fork_secrets_from_current_entry(env: dict[str, str]) -> None:
    current = resolve_run(None, [], env)
    saved = redact(current.settings)
    saved["llm"]["api_key"] = "***"
    saved["llm"]["api_key_file"] = "/run/secrets/old"
    entry(env, "llm", "agents", 'provider = "openai"\nbase_url = "http://llm.test/v1"\napi_key = "sk-new"\n')
    resolved, _ = fork_settings(saved, current.use, {}, [], env)
    assert resolved.settings.llm.api_key == SecretStr("sk-new")


def test_fork_entry_gone(env: dict[str, str]) -> None:
    current = resolve_run(None, [], env)
    use = {**current.use, "llm": "sonnet"}
    with pytest.raises(ConfigError, match=r"unknown llm entry 'sonnet'; llm entries: agents"):
        fork_settings(redact(current.settings), use, {}, [], env)


def test_fork_replaces_block(env: dict[str, str]) -> None:
    entry(env, "llm", "omniroute", OMNIROUTE)
    current = resolve_run(None, ["search.language=es", "use.llm=agents"], env)
    parent_use = {**current.use, "llm": "sonnet"}
    resolved, _ = fork_settings(redact(current.settings), parent_use, {"llm": "omniroute"}, [], env)
    llm = resolved.settings.llm
    assert (llm.base_url, llm.model, llm.context_window) == ("http://ssc:20700/v1", "research-smart", 1048576)
    assert resolved.settings.research.gap_context_tokens == "auto"
    assert resolved.use["llm"] == "omniroute"
    assert resolved.settings.search.language == "es"


def test_fork_applies_profile_model_table(env: dict[str, str]) -> None:
    entry(env, "llm", "omniroute", OMNIROUTE)
    user_profile(env, "p", BASE_PROFILE + '[models.research-smart]\nreasoning = { write = "high" }\n')
    current = resolve_run(None, ["use.llm=agents"], env)
    resolved, _ = fork_settings(redact(current.settings), current.use, {"llm": "omniroute"}, [], env, "p")
    assert resolved.settings.llm.reasoning.write == "high"


def test_fork_profile_gone(env: dict[str, str]) -> None:
    entry(env, "llm", "omniroute", OMNIROUTE)
    current = resolve_run(None, ["use.llm=agents"], env)
    resolved, _ = fork_settings(redact(current.settings), current.use, {"llm": "omniroute"}, [], env, "gone")
    assert resolved.settings.llm.reasoning.write == "low"


def test_toml_quotes_model_ids() -> None:
    tree = {"models": {"qwen3.5:9b": {"reasoning": {"write": "high"}}}, "llm": {"model": "qwen3.5:9b"}}
    assert tomllib.loads(to_toml(tree)) == tree


# Catalog block


def test_catalog_defaults(env: dict[str, str]) -> None:
    catalog = resolve(None, [], env).catalog
    values = (catalog.max_depth, catalog.max_nodes, catalog.pages_per_node, catalog.expand)
    assert values == (3, 200, 2, "both")
    assert (catalog.max_children, catalog.concurrency, catalog.context_tokens) == (50, 4, "auto")


def test_catalog_in_profile(env: dict[str, str]) -> None:
    user_profile(env, "p", BASE_PROFILE + "[catalog]\nmax_nodes = 500\ncontext_tokens = 12000\n")
    catalog = resolve(None, [], env).catalog
    assert (catalog.max_nodes, catalog.context_tokens) == (500, 12000)


def test_catalog_invalid_concurrency(env: dict[str, str]) -> None:
    path = user_profile(env, "p", BASE_PROFILE + "[catalog]\nconcurrency = 0\n")
    with pytest.raises(ConfigError) as error:
        resolve(None, [], env)
    assert str(path) in str(error.value)
    assert "catalog.concurrency" in str(error.value)


def test_preset_cannot_set_catalog(env: dict[str, str]) -> None:
    path = write(env, "depths/big.toml", "[catalog]\nmax_nodes = 900\n")
    with pytest.raises(ConfigError) as error:
        load_depth("big", env)
    assert str(path) in str(error.value)
    assert "catalog.max_nodes" in str(error.value)


def test_structure_wins_over_catalog_block() -> None:
    structure = {
        "fields": [
            {"name": "name", "type": "text", "required": True},
            {"name": "type", "type": "enum", "values": ["a"]},
        ],
        "relation": "r",
        "seeds": [{"name": "S", "type": "a"}],
        "limits": {"max_nodes": 200},
    }
    resolved = catalog_structure(structure, CatalogConfig(max_nodes=500, max_depth=5, expand="links"))
    assert (resolved.limits.max_nodes, resolved.limits.max_depth, resolved.expand) == (200, 5, "links")
    structure["expand"] = "search"
    assert catalog_structure(structure, CatalogConfig(expand="links")).expand == "search"


def test_questions_defaults() -> None:
    questions = Settings().questions
    assert (questions.clarify, questions.rounds, questions.timeout, questions.max_wait) == (True, True, 60, 1800)


def test_questions_timeout_range(env: dict[str, str]) -> None:
    user_profile(env, "bad", BASE_PROFILE + "[questions]\ntimeout = -1\n")
    with pytest.raises(ConfigError, match=r"questions\.timeout"):
        resolve("bad", [], env)


def test_depth_preset_cannot_set_questions(env: dict[str, str]) -> None:
    write(env, "depths/ask.toml", "[questions]\nrounds = false\n")
    with pytest.raises(ConfigError, match=r"questions\.rounds"):
        resolve("p", [], env, "ask")

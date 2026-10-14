"""User profiles and depth presets saved through the API, as TOML files in the configuration directory."""

import os
import re
import tomllib
from collections.abc import Iterable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from wosarcher.config import (
    CUSTOM_DEPTH,
    DEPTH_ORDER,
    LLM_KEYS,
    MODEL_FIELDS,
    RESEARCH_KEYS,
    ConfigError,
    Profile,
    config_dir,
    deep_merge,
    env_layer,
    list_depths,
    list_entries,
    list_profiles,
    pick_entries,
    profile_from,
    read_entry,
    read_profile,
    select_profile,
    set_path,
    to_toml,
    tree_get,
)
from wosarcher.models import DepthUpdate, LLMPatch, ProfileUpdate

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
MANIFEST = "profiles/.nix-managed"


class PresetError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def check_name(kind: str, name: str, existing: Iterable[str]) -> None:
    """The name rule, reserved names, and names taken ignoring case; checked before any path is built."""
    if not NAME.fullmatch(name):
        raise PresetError(
            "invalid_name",
            f"'{name}' is not a valid {kind} name; use letters, digits, - and _, "
            "starting with a letter or digit, up to 64 characters",
        )
    if name.lower() == CUSTOM_DEPTH or (kind == "depth" and name.lower() in DEPTH_ORDER):
        raise PresetError("invalid_name", f"'{name}' is reserved")
    taken = next((other for other in existing if other.lower() == name.lower()), None)
    if taken is not None:
        raise PresetError("name_taken", f"a {kind} named '{taken}' already exists")


def managed_names(env: Mapping[str, str]) -> tuple[set[str], set[str]]:
    """The profiles and the depth presets the NixOS module's manifest lists; none without a manifest."""
    manifest = config_dir(env) / MANIFEST
    lines = manifest.read_text(encoding="utf-8").splitlines() if manifest.is_file() else []
    profiles = {line.removesuffix(".toml") for line in lines if "/" not in line and line.endswith(".toml")}
    depths = {
        line.removeprefix("../depths/").removesuffix(".toml")
        for line in lines
        if line.startswith("../depths/") and line.endswith(".toml")
    }
    return profiles, depths


def write_file(path: Path, text: str) -> None:
    """Write through `.<name>.tmp` in the same directory, mode 0600, then replace the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        os.fchmod(file.fileno(), 0o600)
        file.write(text)
    os.replace(temporary, path)


def managed(kind: str, name: str) -> PresetError:
    return PresetError("managed", f"{kind} '{name}' is managed by the NixOS configuration; it is read-only")


# Profiles


def profile_not_found(name: str) -> PresetError:
    return PresetError("profile_not_found", f"no profile '{name}'")


def checked_use(use: Mapping[str, str], env: Mapping[str, str]) -> None:
    entries = list_entries(env)
    for block, name in use.items():
        if name not in entries[block]:
            listed = ", ".join(entries[block]) or "none"
            raise PresetError("invalid_request", f"use.{block}: unknown entry '{name}'; {block} entries: {listed}")


def tuned_model(base: Profile, use: Mapping[str, str], llm: LLMPatch, env: Mapping[str, str]) -> str:
    """The edited model, else the profile's `llm.model`, else the chosen llm entry's default model."""
    model = llm.model or tree_get(base.data, "llm.model")
    if not model:
        entries = {"llm": list_entries(env)["llm"]}
        chosen = pick_entries(entries, use, env_layer(env)[1], blocks=("llm",))["llm"]
        model = read_entry(chosen).settings.get("model")
    if not model:
        raise PresetError("invalid_request", "llm: no model to save the tuning for; set llm.model")
    return str(model)


def profile_tree(base: Profile, edits: ProfileUpdate, env: Mapping[str, str]) -> dict[str, Any]:
    """The base profile's own keys with run-style edits applied."""
    checked_use(edits.use, env)
    use = {**base.use, **edits.use}
    data = deepcopy(base.data)
    models = deepcopy(base.models)
    llm = edits.llm
    if llm.model is not None:
        set_path(data, ["llm", "model"], llm.model)
    if llm.context_tokens is not None:
        set_path(data, LLM_KEYS["context_tokens"].split("."), llm.context_tokens)
    tuning: dict[str, Any] = {
        field: value
        for field, value in llm.model_dump(include=set(MODEL_FIELDS), exclude_none=True).items()
        if field != "reasoning"
    }
    reasoning = llm.reasoning.model_dump(exclude_none=True)
    if reasoning:
        tuning["reasoning"] = reasoning
    if tuning:
        model = tuned_model(base, use, llm, env)
        models[model] = deep_merge(models.get(model, {}), tuning)
    description = edits.description if edits.description is not None else base.description
    tree: dict[str, Any] = {"description": description} if description else {}
    if use:
        tree["use"] = use
    tree.update(data)
    if models:
        tree["models"] = models
    return tree


def write_profile(name: str, tree: Mapping[str, Any], env: Mapping[str, str]) -> None:
    path = config_dir(env) / "profiles" / f"{name}.toml"
    text = to_toml(tree)
    profile_from(name, path, tomllib.loads(text))
    write_file(path, text)


def base_profile(name: str, env: Mapping[str, str]) -> Profile:
    if name not in list_profiles(env):
        raise profile_not_found(name)
    try:
        return read_profile(name, env)
    except ConfigError as error:
        raise PresetError("invalid_request", str(error)) from None


def save_profile(name: str, base: str, edits: ProfileUpdate, env: Mapping[str, str]) -> None:
    """A new profile from `base` with the edits; a managed base is fine."""
    check_name("profile", name, list_profiles(env))
    write_profile(name, profile_tree(base_profile(base, env), edits, env), env)


def update_profile(name: str, edits: ProfileUpdate, env: Mapping[str, str]) -> None:
    profile = base_profile(name, env)
    if name in managed_names(env)[0]:
        raise managed("profile", name)
    write_profile(name, profile_tree(profile, edits, env), env)


def delete_profile(name: str, env: Mapping[str, str]) -> None:
    available = list_profiles(env)
    if name not in available:
        raise profile_not_found(name)
    if name in managed_names(env)[0]:
        raise managed("profile", name)
    if select_profile(None, env) == name:
        raise PresetError("active_profile", f"profile '{name}' is the active profile; choose another one first")
    available[name].unlink()


# Depth presets


def depth_tree(body: DepthUpdate) -> dict[str, Any]:
    tree: dict[str, Any] = {"description": body.description} if body.description else {}
    values = body.values.model_dump(exclude_none=True)
    keys = {**RESEARCH_KEYS, "words": "write.words"}
    for field, value in values.items():
        set_path(tree, keys[field].split("."), value)
    return tree


def write_depth(name: str, body: DepthUpdate, env: Mapping[str, str]) -> None:
    write_file(config_dir(env) / "depths" / f"{name}.toml", to_toml(depth_tree(body)))


def user_depth(name: str, env: Mapping[str, str]) -> None:
    """Refuse a depth the API may not change: unknown, built-in, or managed."""
    depth = list_depths(env).get(name)
    if depth is None:
        raise PresetError("depth_not_found", f"no depth preset '{name}'")
    if depth.source == "builtin":
        raise PresetError("builtin", f"'{name}' is a built-in depth preset; it is read-only")
    if name in managed_names(env)[1]:
        raise managed("depth preset", name)


def save_depth(name: str, body: DepthUpdate, env: Mapping[str, str]) -> None:
    check_name("depth", name, list_depths(env))
    write_depth(name, body, env)


def replace_depth(name: str, body: DepthUpdate, env: Mapping[str, str]) -> None:
    user_depth(name, env)
    write_depth(name, body, env)


def delete_depth(name: str, env: Mapping[str, str]) -> None:
    user_depth(name, env)
    list_depths(env)[name].path.unlink()

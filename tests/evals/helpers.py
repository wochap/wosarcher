"""Environment for eval tests: the `e2e` profile, a runs directory under `tmp_path`, and the fixture run in it."""

import os
from pathlib import Path

from tests.fixtures.recorded import config_home, copy_fixture


def eval_env(tmp_path: Path) -> tuple[dict[str, str], str]:
    """Subprocess environment and the copied fixture run ID."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("WOSARCHER_")}
    env["XDG_CONFIG_HOME"] = str(config_home(tmp_path / "config"))
    env["WOSARCHER_RUN__RUNS_DIR"] = str(tmp_path / "runs")
    env["WOSARCHER_RUN__CACHE_DIR"] = str(tmp_path / "cache")
    return env, copy_fixture(tmp_path / "runs")

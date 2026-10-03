"""Regenerate `tests/fixtures/runs/20260101-000000-fixture/` from the recorded responses.

Run from the repository root when the contracts change: `uv run python -m tests.fixtures.make_recorded_run`.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from tests.fixtures.recorded import FIXTURE_RUN, NOTES, QUERY, RUNS, config_home, recorded_router
from wosarcher.cli import app


def main() -> int:
    target = RUNS / FIXTURE_RUN
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        os.environ.pop("WOSARCHER_PROFILE", None)
        os.environ["XDG_CONFIG_HOME"] = str(config_home(root / "config"))
        os.environ["WOSARCHER_RUN__RUNS_DIR"] = str(root / "runs")
        os.environ["WOSARCHER_RUN__CACHE_DIR"] = str(root / "cache")
        # The attachment keeps its name only; run from the fixtures directory so no path leaks into the run.
        args = ["run", QUERY, "--profile", "e2e", "--attach", NOTES.name, "--run-id", FIXTURE_RUN]
        cwd = Path.cwd()
        os.chdir(NOTES.parent)
        try:
            with recorded_router():
                result = CliRunner().invoke(app, args)
        finally:
            os.chdir(cwd)
        if result.exit_code != 0:
            print(result.output, file=sys.stderr)
            return result.exit_code
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(root / "runs" / FIXTURE_RUN, target)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

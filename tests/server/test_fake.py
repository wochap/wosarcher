import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from tests.server.conftest import COMMAND, wait_until


def start(runs_dir: Path, mode: str, run_id: str) -> subprocess.Popen[bytes]:
    env = {**os.environ, "WOSARCHER_RUN__RUNS_DIR": str(runs_dir), "FAKE_MODE": mode, "FAKE_STEP": "0.05"}
    argv = [*COMMAND, "run", "q", "--run-id", run_id, "--set", 'write.tone="dry wit"']
    return subprocess.Popen(argv, env=env, stderr=subprocess.PIPE)


def last_type(runs_dir: Path, run_id: str) -> str:
    lines = (runs_dir / run_id / "events.jsonl").read_text().splitlines()
    seqs = [json.loads(line)["seq"] for line in lines]
    assert seqs == list(range(1, len(seqs) + 1))
    return json.loads(lines[-1])["type"]


@pytest.mark.parametrize(("mode", "code", "last"), [("ok", 0, "run.done"), ("slow", 0, "run.done")])
def test_fake_finishes(tmp_path: Path, mode: str, code: int, last: str) -> None:
    process = start(tmp_path, mode, "r")
    assert process.wait(10) == code
    assert last_type(tmp_path, "r") == last
    assert (tmp_path / "r" / "report.md").read_text().endswith("## References\n")
    record = json.loads((tmp_path / "r" / "request.json").read_text())
    assert record["settings"]["write"]["tone"] == "dry wit"


def test_fake_crash(tmp_path: Path) -> None:
    process = start(tmp_path, "crash", "r")
    assert process.wait(10) == 1
    assert last_type(tmp_path, "r") == "stage.started"


def test_fake_term_cancels(tmp_path: Path) -> None:
    process = start(tmp_path, "slow", "r")
    wait_until(lambda: (tmp_path / "r" / "report.md").is_file())
    process.send_signal(signal.SIGTERM)
    assert process.wait(10) == 130
    assert last_type(tmp_path, "r") == "run.cancelled"


def test_fake_ignore_term(tmp_path: Path) -> None:
    process = start(tmp_path, "ignore-term", "r")
    wait_until(lambda: (tmp_path / "r" / "report.md").is_file())
    process.send_signal(signal.SIGTERM)
    time.sleep(0.3)
    assert process.poll() is None
    process.kill()
    process.wait(10)
    assert last_type(tmp_path, "r") == "stage.progress"

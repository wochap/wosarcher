"""`wosarcher run`, `fork`, `runs`, `cancel`, and `doctor` against a served daemon with the fake engine."""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from tests.conftest import Daemon, create_run
from wosarcher.auth import AuthStore
from wosarcher.cli import app
from wosarcher.models import RunOutput
from wosarcher.store import RunStore

runner = CliRunner()
ROOT = Path(__file__).resolve().parent.parent


def listed(daemon: Daemon) -> list[str]:
    return [path.name for path in daemon.runs_dir.iterdir() if not path.name.startswith(".")]


def summary(daemon: Daemon, run_id: str) -> dict[str, object]:
    with httpx.Client(transport=httpx.HTTPTransport(uds=str(daemon.socket)), base_url="http://localhost") as http:
        return http.get(f"/api/runs/{run_id}").json()


def wait_until(condition: object, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():  # pyright: ignore[reportCallIssue]
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.02)


def test_json_done(daemon: Daemon) -> None:
    result = runner.invoke(app, ["run", "q", "--until", "select", "--json"])
    assert result.exit_code == 0, result.output
    output = RunOutput.model_validate_json(result.stdout)
    assert (output.status, output.error) == ("done", None)
    assert output.context is not None
    assert output.report is not None
    record = RunStore(daemon.runs_dir, daemon.runs_dir).read_record(output.run_id)
    assert (record.origin, record.request.until) == ("cli", "select")


def test_json_failed(daemon: Daemon) -> None:
    result = runner.invoke(app, ["run", "crash", "--json"])
    assert result.exit_code == 1
    output = RunOutput.model_validate_json(result.stdout)
    assert output.status == "failed"
    assert output.error is not None
    assert "code 1" in output.error


def test_piped_output_is_report(daemon: Daemon) -> None:
    result = runner.invoke(app, ["run", "q"])
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    assert result.stdout == (daemon.runs_dir / run_id / "report.md").read_text()
    lines = result.stderr.splitlines()
    assert any(" run.started " in line for line in lines)
    assert any(" run.done " in line for line in lines)
    assert not any("\x1b" in line for line in lines)


def test_flags_sent_to_the_server(daemon: Daemon) -> None:
    args = ["run", "q", "--tone", "critical", "--words", "500", "--max-pages", "80", "--search-language", "es-PE"]
    args += ["--allow-domain", "sunat.gob.pe", "--model", "m", "--write-thinking", "high", "--set", "score.top_k=7"]
    assert runner.invoke(app, [*args, "--json"]).exit_code == 0
    [run_id] = listed(daemon)
    sent = json.loads((daemon.runs_dir / run_id / "argv.json").read_text())
    flags = [sent[n + 1] for n, flag in enumerate(sent) if flag == "--set"]
    assert 'write.tone="critical"' in flags
    assert "write.words=500" in flags
    assert "fetch.max_pages=80" in flags
    assert 'search.allow_domains=["sunat.gob.pe"]' in flags
    assert 'search.language="es-PE"' in flags
    assert 'llm.model="m"' in flags
    assert 'llm.reasoning.write="high"' in flags
    assert flags[-1] == "score.top_k=7"


@pytest.mark.parametrize(
    ("args", "named"),
    [
        (["--format", "summary"], "--format"),
        (["--write-thinking", "lots"], "--write-thinking"),
        (["--search-language", "spanish please"], "--search-language"),
        (["--allow-domain", "https://gob.pe/x"], "https://gob.pe/x"),
        (["--sources", "files"], "--sources files needs --attach"),
        (["--until", "rank"], "valid stages"),
    ],
)
def test_checked_before_a_request(daemon: Daemon, args: list[str], named: str) -> None:
    result = runner.invoke(app, ["run", "q", *args])
    assert result.exit_code == 2
    assert named in result.output
    assert not daemon.runs_dir.exists() or listed(daemon) == []


def test_engine_rejects_configuration(daemon: Daemon) -> None:
    result = runner.invoke(app, ["run", "early-exit", "--json"])
    assert result.exit_code == 2
    assert "unknown profile 'x'" in result.stdout


def test_server_rejects_override(daemon: Daemon) -> None:
    result = runner.invoke(app, ["run", "q", "--set", "llm.api_key_file=/etc/shadow"])
    assert result.exit_code == 2
    assert "cannot be set through the API" in result.output


def test_attachments_uploaded(daemon: Daemon, tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    (notes / "sub").mkdir(parents=True)
    (notes / "a.md").write_text("a")
    (notes / "sub" / "b.md").write_text("b")
    result = runner.invoke(app, ["run", "q", "--attach", str(notes), "--sources", "files", "--until", "load", "--json"])
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    assert sorted(path.name for path in (daemon.runs_dir / run_id / "attachments").iterdir()) == ["a.md", "b.md"]


def test_missing_attachment(daemon: Daemon, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "q", "--attach", str(tmp_path / "none*.md")])
    assert result.exit_code == 2
    assert "no file matches" in result.output


def test_run_id_is_not_a_client_flag(daemon: Daemon) -> None:
    result = runner.invoke(app, ["run", "q", "--run-id", "20260101-120000-abcdef"])
    assert result.exit_code == 2
    assert "--run-id" in result.output


def test_daemon_unreachable_creates_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WOSARCHER_SOCKET", str(tmp_path / "nothing.sock"))
    result = runner.invoke(app, ["run", "q"])
    assert result.exit_code == 69


def test_remote_with_token(daemon: Daemon, password_hash: str, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AuthStore(daemon.config_dir / "auth.json")
    store.set_password(password_hash)
    _, token = store.add_token("laptop", datetime.now(UTC))
    monkeypatch.setenv("WOSARCHER_URL", daemon.url)
    monkeypatch.setenv("WOSARCHER_TOKEN", token)
    result = runner.invoke(app, ["run", "q", "--json"])
    assert result.exit_code == 0, result.output
    run_id = RunOutput.model_validate_json(result.stdout).run_id
    runs = json.loads(runner.invoke(app, ["runs", "--json"]).stdout)
    assert [(run["run_id"], run["origin"], run["token_name"]) for run in runs] == [(run_id, "api", "laptop")]


def test_fork(daemon: Daemon) -> None:
    parent = RunOutput.model_validate_json(runner.invoke(app, ["run", "q", "--json"]).stdout).run_id
    result = runner.invoke(app, ["fork", parent, "--from", "write", "--format", "answer", "--until", "write", "--json"])
    assert result.exit_code == 0, result.output
    fork = RunOutput.model_validate_json(result.stdout).run_id
    sent = json.loads((daemon.runs_dir / fork / "argv.json").read_text())
    assert sent[:5] == ["fork", parent, "--from", "write", "--run-id"]
    assert sent[sent.index("--until") + 1] == "write"
    assert 'write.format="answer"' in sent


def test_fork_running_parent(daemon: Daemon) -> None:
    parent = create_run(daemon, "ignore-term")
    wait_until(lambda: (daemon.runs_dir / parent / "report.md").is_file())
    result = runner.invoke(app, ["fork", parent, "--from", "write"])
    assert result.exit_code == 2
    assert "queued or running" in result.output
    runner.invoke(app, ["cancel", parent])


def test_runs_and_cancel(daemon: Daemon) -> None:
    running = create_run(daemon, "ignore-term")
    queued = create_run(daemon)
    wait_until(lambda: (daemon.runs_dir / running / "report.md").is_file())
    assert runner.invoke(app, ["runs"]).exit_code == 0
    rows = json.loads(runner.invoke(app, ["runs", "--json", "--limit", "1"]).stdout)
    assert len(rows) == 1
    cancelled = runner.invoke(app, ["cancel", queued])
    assert cancelled.output.strip() == f"run {queued}: dequeued"
    assert runner.invoke(app, ["cancel", running]).output.strip() == f"run {running}: signalled"
    wait_until(lambda: summary(daemon, running).get("status") == "cancelled")
    finished = runner.invoke(app, ["cancel", running])
    assert finished.exit_code == 2
    assert "status cancelled" in finished.output
    assert runner.invoke(app, ["cancel", "nope"]).exit_code == 2


def test_waiting_shown(daemon: Daemon, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_STEP", "0.02")
    first = create_run(daemon, "slow")
    result = runner.invoke(app, ["run", "q", "--json"])
    assert result.exit_code == 0, result.output
    assert "waiting for a free run slot (position 1)" in result.stderr
    assert summary(daemon, first)["status"] == "done"


def client(daemon: Daemon, *args: str) -> "subprocess.Popen[str]":
    env = {**os.environ, "WOSARCHER_SOCKET": str(daemon.socket)}
    argv = [sys.executable, "-m", "wosarcher", "run", *args]
    return subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def newest(daemon: Daemon, before: set[str]) -> str:
    with httpx.Client(transport=httpx.HTTPTransport(uds=str(daemon.socket)), base_url="http://localhost") as http:
        found = [run["run_id"] for run in http.get("/api/runs").json() if run["run_id"] not in before]
    return found[0] if found else ""


def test_ctrl_c_while_queued(daemon: Daemon) -> None:
    holder = create_run(daemon, "ignore-term")
    wait_until(lambda: (daemon.runs_dir / holder / "report.md").is_file())
    process = client(daemon, "q", "--json")
    wait_until(lambda: newest(daemon, {holder}) != "")
    run_id = newest(daemon, {holder})
    wait_until(lambda: summary(daemon, run_id).get("status") == "queued")
    time.sleep(0.3)
    process.send_signal(signal.SIGINT)
    assert process.wait(timeout=15) == 130
    assert summary(daemon, run_id)["status"] == "cancelled"
    runner.invoke(app, ["cancel", holder])


def test_ctrl_c_while_running(daemon: Daemon, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_STEP", "0.2")
    process = client(daemon, "slow", "--json")
    wait_until(lambda: newest(daemon, set()) != "")
    run_id = newest(daemon, set())
    wait_until(lambda: (daemon.runs_dir / run_id / "report.md").is_file())
    process.send_signal(signal.SIGINT)
    assert process.wait(timeout=15) == 130
    events = (daemon.runs_dir / run_id / "events.jsonl").read_text().splitlines()
    assert json.loads(events[-1])["type"] == "run.cancelled"


def test_doctor(daemon: Daemon, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_DOCTOR", "failed")
    result = runner.invoke(app, ["doctor", "--block", "score", "--json"])
    assert result.exit_code == 1, result.output
    checks = json.loads(result.stdout)["checks"]
    assert [(check["role"], check["status"]) for check in checks] == [("score", "down")]
    monkeypatch.setenv("FAKE_DOCTOR", "ok")
    table = runner.invoke(app, ["doctor"])
    assert table.exit_code == 0, table.output
    assert "searxng" in table.output

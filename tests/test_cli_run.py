"""`wosarcher run`, `fork`, `runs`, `cancel`, and `doctor` against a served daemon with the fake engine."""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from tests.conftest import Daemon, StartDaemon, create_run
from tests.server.test_catalog import fixed
from tests.stages.catalog_data import structure_data
from wosarcher.adapters.fakes import FakeLLM
from wosarcher.auth import AuthStore
from wosarcher.cli import app
from wosarcher.models import Completion, Effort, Message, RunOutput
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
        (["--use", "scorer=bm25"], "--use"),
        (["--context-window", "0"], "--context-window"),
    ],
)
def test_checked_before_a_request(daemon: Daemon, args: list[str], named: str) -> None:
    result = runner.invoke(app, ["run", "q", *args])
    assert result.exit_code == 2
    assert named in result.output
    assert not daemon.runs_dir.exists() or listed(daemon) == []


def test_unknown_block_in_entry_flag(daemon: Daemon) -> None:
    result = runner.invoke(app, ["run", "q", "--use", "scorer=bm25"], env={"COLUMNS": "200"})
    assert result.exit_code == 2
    assert "unknown block 'scorer'; choose from search, fetch, prefilter, score, llm" in result.output


def test_entry_flag(daemon: Daemon, config_dir: Path) -> None:
    (config_dir / "providers" / "score").mkdir()
    (config_dir / "providers" / "score" / "jev-strict.toml").write_text('provider = "jev"\n')
    result = runner.invoke(app, ["run", "q", "--use", "score=jev-strict", "--use", "llm=agents", "--json"])
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    sent = json.loads((daemon.runs_dir / run_id / "argv.json").read_text())
    assert [sent[n + 1] for n, flag in enumerate(sent) if flag == "--use"] == ["score=jev-strict", "llm=agents"]
    record = RunStore(daemon.runs_dir, daemon.runs_dir).read_record(run_id)
    assert (record.use or {})["score"] == "jev-strict"


def test_unknown_entry_rejected_by_server(daemon: Daemon) -> None:
    result = runner.invoke(app, ["run", "q", "--use", "llm=sonet"])
    assert result.exit_code == 2
    assert "use.llm: unknown entry 'sonet'; llm entries: agents" in result.output
    assert not daemon.runs_dir.exists() or listed(daemon) == []


def test_limits_for_an_unlisted_model(daemon: Daemon) -> None:
    args = ["run", "q", "--model", "qwen3-30b-a3b", "--context-window", "262144", "--max-output", "16384"]
    assert runner.invoke(app, [*args, "--context-tokens", "auto", "--json"]).exit_code == 0
    [run_id] = listed(daemon)
    settings = RunStore(daemon.runs_dir, daemon.runs_dir).read_record(run_id).settings
    assert (settings["llm"]["context_window"], settings["llm"]["max_output_tokens"]) == (262144, 16384)
    assert settings["select"]["max_context_tokens"] == "auto"


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


def run_client(daemon: Daemon, env: dict[str, str], *args: str) -> "subprocess.CompletedProcess[str]":
    """The client in its own process, so only it sees `env`; the daemon's environment stays as is."""
    full = {**os.environ, "WOSARCHER_SOCKET": str(daemon.socket), **env}
    argv = [sys.executable, "-m", "wosarcher", *args]
    return subprocess.run(argv, cwd=ROOT, env=full, capture_output=True, text=True, timeout=60, check=False)


def profiles_named(config_dir: Path, *names: str) -> None:
    for name in names:
        (config_dir / "profiles" / f"{name}.toml").write_text('[use]\nprefilter = "bm25"\n')


def test_depth_from_the_environment(daemon: Daemon) -> None:
    result = run_client(daemon, {"WOSARCHER_DEPTH": "quick"}, "run", "q", "--until", "select", "--json")
    assert result.returncode == 0, result.stderr
    record = RunStore(daemon.runs_dir, daemon.runs_dir).read_record(RunOutput.model_validate_json(result.stdout).run_id)
    assert record.request.depth == "quick"
    assert record.settings["fetch"]["max_pages"] == 15


def test_flags_win_over_the_environment(daemon: Daemon, config_dir: Path) -> None:
    profiles_named(config_dir, "lan", "cloud")
    env = {"WOSARCHER_DEPTH": "quick", "WOSARCHER_PROFILE": "lan"}
    result = run_client(daemon, env, "run", "q", "--depth", "deep", "--profile", "cloud", "--json")
    assert result.returncode == 0, result.stderr
    record = RunStore(daemon.runs_dir, daemon.runs_dir).read_record(RunOutput.model_validate_json(result.stdout).run_id)
    assert (record.request.depth, record.profile) == ("deep", "cloud")


def test_profile_from_the_environment(daemon: Daemon, config_dir: Path) -> None:
    profiles_named(config_dir, "lan", "desktop")
    (config_dir / "current").write_text("desktop\n")
    result = run_client(daemon, {"WOSARCHER_PROFILE": "lan"}, "run", "q", "--json")
    assert result.returncode == 0, result.stderr
    record = RunStore(daemon.runs_dir, daemon.runs_dir).read_record(RunOutput.model_validate_json(result.stdout).run_id)
    assert record.profile == "lan"


def test_empty_depth_variable(daemon: Daemon) -> None:
    result = run_client(daemon, {"WOSARCHER_DEPTH": ""}, "run", "q", "--json")
    assert result.returncode == 0, result.stderr
    record = RunStore(daemon.runs_dir, daemon.runs_dir).read_record(RunOutput.model_validate_json(result.stdout).run_id)
    assert record.request.depth is None


def test_unknown_depth_from_the_environment(daemon: Daemon) -> None:
    result = run_client(daemon, {"WOSARCHER_DEPTH": "quik"}, "run", "q")
    assert result.returncode == 2
    assert "depth: unknown depth 'quik'" in result.stderr
    assert not daemon.runs_dir.exists() or listed(daemon) == []


def test_depth_in_the_daemon_environment(daemon: Daemon, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WOSARCHER_DEPTH", "quick")
    result = runner.invoke(app, ["run", "q", "--json"])
    assert result.exit_code == 0, result.output
    assert RunOutput.model_validate_json(result.stdout).status == "done"


def test_fork_ignores_the_environment(daemon: Daemon, config_dir: Path) -> None:
    profiles_named(config_dir, "cloud")
    parent = RunOutput.model_validate_json(runner.invoke(app, ["run", "q", "--json"]).stdout).run_id
    env = {"WOSARCHER_PROFILE": "cloud"}
    result = run_client(daemon, env, "fork", parent, "--from", "write", "--tone", "critical", "--json")
    assert result.returncode == 0, result.stderr
    fork = RunOutput.model_validate_json(result.stdout).run_id
    store = RunStore(daemon.runs_dir, daemon.runs_dir)
    assert store.read_record(fork).profile == store.read_record(parent).profile == "workstation"


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


def test_doctor(daemon: Daemon, config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (config_dir / "providers" / "score").mkdir()
    (config_dir / "providers" / "score" / "rerank.toml").write_text('provider = "rerank"\nbase_url = "http://r"\n')
    (config_dir / "profiles" / "workstation.toml").write_text('[use]\nprefilter = "bm25"\nscore = "rerank"\n')
    monkeypatch.setenv("FAKE_DOCTOR", "failed")
    result = runner.invoke(app, ["doctor", "--block", "score", "--json"])
    assert result.exit_code == 1, result.output
    entries = json.loads(result.stdout)["entries"]
    assert [(entry["block"], entry["name"], entry["status"]) for entry in entries] == [("score", "rerank", "down")]
    assert json.loads((daemon.runs_dir / "doctor-argv.json").read_text())[-1] == "--entry=score=rerank"
    monkeypatch.setenv("FAKE_DOCTOR", "ok")
    table = runner.invoke(app, ["doctor", "--use", "score=bm25"], env={"COLUMNS": "200"})
    assert table.exit_code == 0, table.output
    assert "searxng" in table.output


def test_doctor_profile_from_the_environment(daemon: Daemon, config_dir: Path) -> None:
    (config_dir / "providers" / "score").mkdir()
    (config_dir / "providers" / "score" / "rerank.toml").write_text('provider = "rerank"\nbase_url = "http://r"\n')
    (config_dir / "profiles" / "cloud.toml").write_text('[use]\nprefilter = "bm25"\nscore = "rerank"\n')
    (config_dir / "profiles" / "desktop.toml").write_text('[use]\nprefilter = "bm25"\nscore = "bm25"\n')
    (config_dir / "current").write_text("desktop\n")
    result = run_client(daemon, {"WOSARCHER_PROFILE": "cloud"}, "doctor", "--block", "score", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["profile"] == "cloud"
    assert [(entry["block"], entry["name"]) for entry in report["entries"]] == [("score", "rerank")]
    flag = run_client(
        daemon, {"WOSARCHER_PROFILE": "cloud"}, "doctor", "--profile", "desktop", "--block", "score", "--json"
    )
    assert flag.returncode == 0, flag.stderr
    assert json.loads(flag.stdout)["profile"] == "desktop"
    assert [entry["name"] for entry in json.loads(flag.stdout)["entries"]] == ["bm25"]


# Catalog


def structure_file(tmp_path: Path, **changes: object) -> Path:
    path = tmp_path / "peru.json"
    path.write_text(json.dumps(structure_data(**changes)))
    return path


def request_of(daemon: Daemon, run_id: str) -> dict[str, Any]:
    return json.loads((daemon.runs_dir / run_id / "request.json").read_text())


def test_catalog_structure_file(daemon: Daemon, tmp_path: Path) -> None:
    path = structure_file(tmp_path)
    result = runner.invoke(
        app, ["catalog", "Every public organization", "--structure", str(path), "--allow-domain", "gob.pe"]
    )
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    record = request_of(daemon, run_id)
    assert record["request"]["kind"] == "catalog"
    assert record["request"]["structure"]["relation"] == "organismos adscritos"
    assert record["form"]["domains"]["allow"] == ["gob.pe"]
    assert json.loads(result.stdout) == [{"id": "n0", "name": "Poder Ejecutivo", "type": "power"}]


def test_catalog_flags_over_the_file(daemon: Daemon, tmp_path: Path) -> None:
    path = structure_file(tmp_path)
    args = ["catalog", "b", "--structure", str(path), "--max-nodes", "50", "--seed", "PCM|ministry|https://pcm.test"]
    args += ["--leaf", "agency", "--expand", "links", "--search-language", "es", "--json"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    structure = request_of(daemon, run_id)["request"]["structure"]
    assert structure["limits"]["max_nodes"] == 50
    assert structure["seeds"] == [{"name": "PCM", "type": "ministry", "url": "https://pcm.test"}]
    assert (structure["leaf_types"], structure["expand"], structure["language"]) == (["agency"], "links", "es")
    assert json.loads(result.stdout)["reason"] == "frontier empty"


def test_catalog_derived_structure(daemon: Daemon) -> None:
    result = runner.invoke(app, ["catalog", "brief"])
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    assert "--structure" not in json.loads((daemon.runs_dir / run_id / "argv.json").read_text())


def test_catalog_structure_from_flags(daemon: Daemon) -> None:
    result = runner.invoke(
        app, ["catalog", "b", "--seed", "PCM|ministry", "--relation", "adscritos", "--leaf", "office"]
    )
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    structure = request_of(daemon, run_id)["request"]["structure"]
    assert structure["relation"] == "adscritos"
    assert next(f for f in structure["fields"] if f["type"] == "enum")["values"] == ["ministry", "office"]


def test_catalog_until_prints_nothing(daemon: Daemon) -> None:
    result = runner.invoke(app, ["catalog", "b", "--until", "extract"])
    assert result.exit_code == 0, result.output
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("args", "named"),
    [
        (["--seed", "PCM|ministry"], "--relation"),
        (["--seed", "PCM"], "--seed"),
        (["--expand", "crawl"], "--expand"),
        (["--output", "summary"], "--output"),
        (["--max-nodes", "0"], "--max-nodes"),
        (["--until", "score"], "catalog stage"),
        (["--sources", "files"], "--sources"),
        (["--search-language", "spanish"], "--search-language"),
        (["--allow-domain", "gob.pe/x"], "gob.pe/x"),
        (["--use", "scorer=bm25"], "--use"),
        (["--extract-thinking", "max"], "--extract-thinking"),
        (["--write-thinking", "high"], "--write-thinking"),
    ],
)
def test_catalog_checked_before_a_request(daemon: Daemon, args: list[str], named: str) -> None:
    result = runner.invoke(app, ["catalog", "b", *args])
    assert result.exit_code == 2
    assert named in result.output
    assert not daemon.runs_dir.exists() or listed(daemon) == []


def test_catalog_report_output(daemon: Daemon, tmp_path: Path) -> None:
    path = structure_file(tmp_path)
    result = runner.invoke(app, ["catalog", "b", "--structure", str(path), "--output", "report", "--words", "800"])
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    record = request_of(daemon, run_id)
    assert record["request"]["structure"]["output"] == "report"
    assert record["form"]["writing"]["words"] == 800
    assert "write.words=800" in json.loads((daemon.runs_dir / run_id / "argv.json").read_text())
    assert result.stdout.startswith("Poder Ejecutivo heads the catalog [1].")


def test_catalog_writing_flag_without_a_report(daemon: Daemon, tmp_path: Path) -> None:
    result = runner.invoke(app, ["catalog", "b", "--structure", str(structure_file(tmp_path)), "--tone", "critical"])
    assert result.exit_code == 2
    assert "--tone" in result.output
    assert "--output" in result.output
    assert not daemon.runs_dir.exists() or listed(daemon) == []


def test_catalog_json_with_a_report(daemon: Daemon, tmp_path: Path) -> None:
    path = structure_file(tmp_path)
    result = runner.invoke(app, ["catalog", "b", "--structure", str(path), "--output", "both", "--json"])
    assert result.exit_code == 0, result.output
    found = json.loads(result.stdout)
    assert found["records"][0]["name"] == "Poder Ejecutivo"
    assert found["output"] == "both"
    assert found["report"]["body"] == "Poder Ejecutivo heads the catalog [1]."
    assert "references" in found["report"]


def test_catalog_thinking_flags(daemon: Daemon) -> None:
    result = runner.invoke(app, ["catalog", "b", "--extract-thinking", "low", "--draft-thinking", "high"])
    assert result.exit_code == 0, result.output
    [run_id] = listed(daemon)
    overrides = request_of(daemon, run_id)["overrides"]
    assert {'llm.reasoning.extract="low"', 'llm.reasoning.draft="high"'} <= set(overrides)


def test_fork_reextract_with_a_level(daemon: Daemon) -> None:
    assert runner.invoke(app, ["catalog", "b"]).exit_code == 0
    [parent] = listed(daemon)
    result = runner.invoke(app, ["fork", parent, "--from", "extract", "--extract-thinking", "medium", "--json"])
    assert result.exit_code == 0, result.output
    fork = next(run_id for run_id in listed(daemon) if run_id != parent)
    assert 'llm.reasoning.extract="medium"' in request_of(daemon, fork)["overrides"]


def test_fork_flag_of_the_other_kind(daemon: Daemon) -> None:
    parent = RunOutput.model_validate_json(runner.invoke(app, ["run", "q", "--json"]).stdout).run_id
    result = runner.invoke(app, ["fork", parent, "--from", "write", "--extract-thinking", "low"])
    assert result.exit_code == 2
    assert "--extract-thinking" in result.output
    assert "research" in result.output
    assert listed(daemon) == [parent]


def test_catalog_invalid_structure(daemon: Daemon, tmp_path: Path) -> None:
    result = runner.invoke(app, ["catalog", "b", "--structure", str(structure_file(tmp_path)), "--leaf", "moon"])
    assert result.exit_code == 2
    assert "leaf type 'moon'" in result.output
    assert not daemon.runs_dir.exists() or listed(daemon) == []


def test_catalog_draft(start_daemon: StartDaemon, tmp_path: Path) -> None:
    llm = FakeLLM([json.dumps(structure_data())])
    daemon = start_daemon(draft_llm=fixed(llm))
    result = runner.invoke(app, ["catalog", "draft", "Every public organization"])
    assert result.exit_code == 0, result.output
    assert listed(daemon) == [] if daemon.runs_dir.exists() else True
    path = tmp_path / "drafted.json"
    path.write_text(result.stdout)
    again = runner.invoke(app, ["catalog", "Every public organization", "--structure", str(path)])
    assert again.exit_code == 0, again.output


class Down:
    async def complete(
        self, messages: list[Message], *, max_tokens: int, effort: Effort, temperature: float | None = None
    ) -> Completion:
        raise ConnectionError("connection refused")


def test_catalog_draft_failed(start_daemon: StartDaemon) -> None:
    start_daemon(draft_llm=fixed(Down()))
    result = runner.invoke(app, ["catalog", "draft", "brief"])
    assert result.exit_code == 1
    assert "connection refused" in result.output


def test_catalog_draft_rejects_run_flags(daemon: Daemon) -> None:
    result = runner.invoke(app, ["catalog", "draft", "brief", "--max-nodes", "5"])
    assert result.exit_code == 2
    assert "--max-nodes" in result.output


def test_runs_kind(daemon: Daemon, tmp_path: Path) -> None:
    assert runner.invoke(app, ["catalog", "b", "--structure", str(structure_file(tmp_path))]).exit_code == 0
    assert runner.invoke(app, ["run", "q", "--json"]).exit_code == 0
    table = runner.invoke(app, ["runs"])
    assert "catalog" in table.stdout
    research = json.loads(runner.invoke(app, ["runs", "--kind", "research", "--json"]).stdout)
    assert [row["kind"] for row in research] == ["research"]
    catalogs = json.loads(runner.invoke(app, ["runs", "--kind", "catalog", "--json"]).stdout)
    assert [(row["kind"], row["nodes"], row["writing"]) for row in catalogs] == [("catalog", 1, None)]
    assert runner.invoke(app, ["runs", "--kind", "other"]).exit_code == 2


def test_catalog_progress_rows() -> None:
    import io

    from rich.console import Console

    from wosarcher.cli.progress import ProgressView
    from wosarcher.models import CatalogDoneData, StageDoneData, StageStartedData, WaveDoneData, make_event

    def event(event_type: str, stage: str, data: object) -> Any:
        return make_event(1, "r", datetime.now(UTC), event_type, stage, data)  # pyright: ignore[reportArgumentType]

    out = io.StringIO()
    view = ProgressView(Console(file=out, force_terminal=False, width=200), kind="catalog")
    assert list(view.rows) == ["load", "draft", "expand", "search", "fetch", "chunk", "extract", "assemble", "write"]
    view.update(event("stage.started", "fetch", StageStartedData(device=None, provider="firecrawl", round=2)))
    assert view.rows["fetch"].state == "running · wave 2"
    view.update(event("stage.done", "fetch", StageDoneData(count=5, seconds=1.0, round=2)))
    assert view.rows["fetch"].state == "done · wave 2"
    view.update(
        event("wave.done", "extract", WaveDoneData(wave=2, expanded=3, found=9, records=3, failed=1, dropped=0))
    )
    assert view.rows["extract"].counters == "wave 2: 3 records, 1 failed"
    done = CatalogDoneData(waves=2, nodes=9, records=8, flagged=1, reason="max nodes", note="")
    view.update(event("catalog.done", "assemble", done))
    assert "catalog: 8 records in 2 waves · 1 flagged · max nodes" in out.getvalue()

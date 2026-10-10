"""Replay forks recorded runs with variants through `wosarcherd fork` and records one result per pair."""

import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from evals.replay import VARIANTS, Variant, VariantError, fork, load_variants, main, read_results
from tests.evals.helpers import eval_env
from tests.fixtures.recorded import HTTP
from wosarcher.models import StageDone, parse_event


def test_shipped_variants_load() -> None:
    variants = load_variants(VARIANTS)
    assert {"bm25", "bm25-wide", "rerank", "jev", "prefilter-embeddings", "prefilter-bm25"} <= set(variants)
    assert variants["bm25"] == Variant(name="bm25", from_stage="score", set=["score.provider=bm25"])
    assert variants["chunk-current"] == Variant(name="chunk-current", from_stage="chunk", set=[])
    assert variants["write-current"] == Variant(name="write-current", from_stage="write", set=[])


def test_invalid_stage_names_variant(tmp_path: Path) -> None:
    path = tmp_path / "variants.toml"
    path.write_text('[early]\nfrom = "fetch"\nset = []\n')
    with pytest.raises(VariantError, match=r"variant 'early'.*chunk, prefilter, score, write"):
        load_variants(path)


def test_fork_bm25(tmp_path: Path) -> None:
    env, parent = eval_env(tmp_path)
    result = fork(parent, load_variants(VARIANTS)["bm25"], write=False, env=env, runs_dir=tmp_path / "runs")
    assert (result.status, result.parent_run_id, result.variant) == ("done", parent, "bm25")
    assert result.run_id not in (None, parent)


def test_failed_fork_keeps_error(tmp_path: Path) -> None:
    env, parent = eval_env(tmp_path)
    variant = Variant(name="typo", from_stage="score", set=["score.topk=1"])
    result = fork(parent, variant, write=False, env=env, runs_dir=tmp_path / "runs")
    assert (result.status, result.run_id) == ("failed", None)
    assert result.error is not None
    assert "score.topk" in result.error


def test_two_runs_two_variants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, parent = eval_env(tmp_path)
    second = "20260101-000001-second"
    args = ["fork", parent, "--from", "prefilter", "--until", "select", "--run-id", second]
    subprocess.run([sys.executable, "-m", "wosarcher.daemon", *args], env=env, check=True, capture_output=True)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    argv = ["--runs", parent, second, "--variants", "bm25", "bm25-wide", "--out", str(out)]
    assert main(argv) == 0
    results = read_results(out / "results.jsonl")
    assert len(results) == 4
    assert {(r.parent_run_id, r.variant, r.status) for r in results} == {
        (run, name, "done") for run in (parent, second) for name in ("bm25", "bm25-wide")
    }
    assert main(argv) == 0
    assert len(read_results(out / "results.jsonl")) == 4


def test_search_and_fetch_held_constant(tmp_path: Path) -> None:
    env, parent = eval_env(tmp_path)
    result = fork(parent, load_variants(VARIANTS)["bm25"], write=False, env=env, runs_dir=tmp_path / "runs")
    assert result.run_dir is not None
    fork_dir, parent_dir = Path(result.run_dir), tmp_path / "runs" / parent
    events = [parse_event(line) for line in (fork_dir / "events.jsonl").read_text().splitlines()]
    done = {event.stage: event for event in events if isinstance(event, StageDone)}
    for stage in ("search", "fetch", "chunk"):
        assert done[stage].data.copied_from == parent
    for name in ("hits.jsonl", "chunks.jsonl"):
        assert (fork_dir / name).read_bytes() == (parent_dir / name).read_bytes()


def test_chunk_variant_rechunks_parent_pages(tmp_path: Path) -> None:
    env, parent = eval_env(tmp_path)
    result = fork(parent, load_variants(VARIANTS)["chunk-current"], write=False, env=env, runs_dir=tmp_path / "runs")
    assert result.status == "done"
    assert result.run_dir is not None
    fork_dir, parent_dir = Path(result.run_dir), tmp_path / "runs" / parent
    events = [parse_event(line) for line in (fork_dir / "events.jsonl").read_text().splitlines()]
    done = {event.stage: event for event in events if isinstance(event, StageDone)}
    for stage in ("search", "fetch"):
        assert done[stage].data.copied_from == parent
    assert done["chunk"].data.copied_from is None
    assert (fork_dir / "hits.jsonl").read_bytes() == (parent_dir / "hits.jsonl").read_bytes()


class RecordedChat(BaseHTTPRequestHandler):
    """Answers every chat request with the recorded streamed report."""

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        body = (HTTP / "llm" / "write.sse").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_write_variant_rewrites_report_only(tmp_path: Path) -> None:
    env, parent = eval_env(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordedChat)
    Thread(target=server.serve_forever, daemon=True).start()
    llm = f'llm.base_url="http://127.0.0.1:{server.server_port}/v1"'
    try:
        result = fork(
            parent,
            load_variants(VARIANTS)["write-current"],
            write=False,
            env=env,
            runs_dir=tmp_path / "runs",
            extra=[llm],
        )
    finally:
        server.shutdown()
    assert result.status == "done", result.error
    assert result.run_dir is not None
    fork_dir, parent_dir = Path(result.run_dir), tmp_path / "runs" / parent
    events = [parse_event(line) for line in (fork_dir / "events.jsonl").read_text().splitlines()]
    done = {event.stage: event for event in events if isinstance(event, StageDone)}
    for stage in ("search", "fetch", "chunk", "prefilter", "score", "select"):
        assert done[stage].data.copied_from == parent
    assert done["write"].data.copied_from is None
    assert (fork_dir / "context.json").read_bytes() == (parent_dir / "context.json").read_bytes()
    assert (fork_dir / "report.md").is_file()


DEAD = "http://127.0.0.1:9"


def test_scorer_fallback_fails_fork(tmp_path: Path) -> None:
    env, parent = eval_env(tmp_path)
    variant = Variant(name="jev", from_stage="score", set=["score.provider=jev", f"score.base_url={DEAD}"])
    result = fork(parent, variant, write=False, env=env, runs_dir=tmp_path / "runs")
    assert result.status == "failed"
    assert result.run_id not in (None, parent)
    assert result.run_dir is not None
    assert result.error is not None
    assert result.error.startswith("score ran bm25 instead of jev: jev: ")


def test_prefilter_fallback_fails_fork(tmp_path: Path) -> None:
    env, parent = eval_env(tmp_path)
    overrides = ["prefilter.provider=embeddings", f"prefilter.base_url={DEAD}", "prefilter.model=e"]
    variant = Variant(name="emb", from_stage="prefilter", set=overrides)
    result = fork(parent, variant, write=False, env=env, runs_dir=tmp_path / "runs")
    assert (result.status, result.error) == ("failed", "prefilter ran bm25 instead of embeddings")
    assert result.run_id is not None
    assert result.run_dir is not None


def test_small_input_passthrough_stays_done(tmp_path: Path) -> None:
    env, parent = eval_env(tmp_path)
    variant = Variant(name="small", from_stage="prefilter", set=["select.passthrough_chars=1000000"])
    result = fork(parent, variant, write=False, env=env, runs_dir=tmp_path / "runs")
    assert (result.status, result.error) == ("done", None)

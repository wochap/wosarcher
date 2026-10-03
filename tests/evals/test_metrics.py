"""Metrics without an LLM, on hand-written run directories and on real replay results."""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

import evals.replay as replay
from evals.metrics import ResultMetrics, context_size, jaccard, main, selected_chunk_ids, stage_seconds
from tests.evals.helpers import eval_env
from wosarcher.models import Context, Passage, Stage, StageDoneData, make_event


def write_run(run_dir: Path, texts: dict[str, str], seconds: dict[Stage, tuple[float, str | None]]) -> None:
    run_dir.mkdir(parents=True)
    passages = [
        Passage(n=n, chunk_id=chunk, source_id="s", query_id="q0", text=text, scorer="bm25")
        for n, (chunk, text) in enumerate(texts.items(), start=1)
    ]
    found = Context(query="q", passages=passages, sources=[], budget_tokens=100, used_tokens=0)
    (run_dir / "context.json").write_text(found.model_dump_json())
    now = datetime.now(UTC)
    lines = [
        make_event(seq, "r", now, "stage.done", stage, StageDoneData(count=1, seconds=took, copied_from=parent))
        for seq, (stage, (took, parent)) in enumerate(seconds.items(), start=1)
    ]
    (run_dir / "events.jsonl").write_text("".join(event.model_dump_json() + "\n" for event in lines))


def test_jaccard() -> None:
    assert jaccard({"1", "2", "3"}, {"2", "3", "4"}) == 0.5
    assert jaccard(set(), set()) == 1.0


def test_run_directory_metrics(tmp_path: Path) -> None:
    write_run(
        tmp_path / "r",
        {"c1": "x" * 10, "c2": "y" * 3},
        {"search": (4.0, "parent"), "fetch": (9.0, "parent"), "score": (1.2, None), "select": (0.1, None)},
    )
    assert selected_chunk_ids(tmp_path / "r") == ["c1", "c2"]
    assert context_size(tmp_path / "r") == (13, 4)
    assert stage_seconds(tmp_path / "r") == {"score": 1.2, "select": 0.1}


def test_metrics_over_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env, parent = eval_env(tmp_path)
    second = "20260101-000001-second"
    args = ["fork", parent, "--from", "prefilter", "--until", "select", "--run-id", second]
    subprocess.run([sys.executable, "-m", "wosarcher", *args], env=env, check=True, capture_output=True)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, second, "--variants", "bm25", "bm25-wide", "--out", str(out)]) == 0
    capsys.readouterr()
    assert main(["--results", str(out)]) == 0
    table = capsys.readouterr().out
    rows = [line for line in table.splitlines() if line.startswith("| bm25")]
    assert [row.split("|")[1].strip() for row in rows] == ["bm25", "bm25-wide"]
    measured = [ResultMetrics.model_validate(item) for item in json.loads((out / "metrics.json").read_text())]
    assert len(measured) == 4
    assert all(item.passages > 0 and "score" in item.seconds and "fetch" not in item.seconds for item in measured)
    assert all(set(item.overlap) == {"bm25", "bm25-wide"} - {item.variant} for item in measured)

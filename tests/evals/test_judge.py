"""Judged precision with the fake LLM: parsing, message separation, and stored judgements."""

from pathlib import Path

import httpx
import pytest

import evals.judge as judge
import evals.replay as replay
import wosarcher.build as building
from tests.evals.helpers import eval_env
from tests.runner.helpers import adapters
from wosarcher.adapters.fakes import FakeLLM
from wosarcher.config import Settings
from wosarcher.http import UsageLedger
from wosarcher.models import Context, Passage, Report
from wosarcher.ports import Adapters

PASSAGES = ["Lithium is recovered.", "Unrelated {text} with $query and <data>.", "Cobalt prices.", "Weather."]


async def test_precision() -> None:
    assert await judge.judge_result(FakeLLM(["Relevant: [0, 2]"]), "battery recycling", PASSAGES) == 0.5


async def test_unparsable_answer() -> None:
    assert await judge.judge_result(FakeLLM(["passages one and three"]), "battery recycling", PASSAGES) is None


async def test_passages_in_separate_message() -> None:
    llm = FakeLLM(["[]"])
    assert await judge.judge_result(llm, "battery recycling", PASSAGES) == 0.0
    system, user = llm.calls[0]
    assert (system.role, user.role) == ("system", "user")
    assert "battery recycling" in system.content
    assert all(text not in system.content for text in PASSAGES)
    assert all(text in user.content for text in PASSAGES)


def test_second_call_skips_judged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", "bm25", "--out", str(out)]) == 0
    llm = FakeLLM(["[0]"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    assert len(llm.calls) == 1
    (judged,) = judge.read_judgements(out / "judgements.jsonl")
    assert judged.precision is not None
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    assert len(llm.calls) == 1


def test_parse_answer_malformed_list() -> None:
    assert judge.parse_answer("[1, 2,]", 4) is None


def test_malformed_list_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", "bm25", "bm25-wide", "--out", str(out)]) == 0
    llm = FakeLLM(["[1, 2,]", "[0]"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    first, second = judge.read_judgements(out / "judgements.jsonl")
    assert first.precision is None
    assert second.precision is not None


def report(body: str) -> Report:
    return Report(body=body, markdown=body, cited=[], references=[])


def passages(count: int) -> Context:
    return Context(
        query="q",
        passages=[
            Passage(n=n, chunk_id=f"c{n}", source_id="s", query_id="q", text=f"passage {n}", scorer="bm25")
            for n in range(1, count + 1)
        ],
        sources=[],
        budget_tokens=0,
        used_tokens=0,
    )


def test_claims() -> None:
    pairs = judge.claims(report("A is true [1]. B and C hold [2, 3]. Lost [9]."), passages(3))
    assert pairs == [
        ("A is true", "passage 1"),
        ("B and C hold", "passage 2"),
        ("B and C hold", "passage 3"),
    ]
    assert judge.claims(report("See [1](https://example.com)."), passages(1)) == []


PAIRS = [("A is true", "passage 1"), ("B and C hold", "passage 2"), ("B and C hold", "passage 3")]


async def test_faithfulness() -> None:
    llm = FakeLLM(["[0, 2]"])
    score = await judge.judge_faithfulness(llm, "battery recycling", PAIRS)
    assert score is not None
    assert round(score, 2) == 0.67
    system, user = llm.calls[0]
    assert "battery recycling" in system.content
    assert all(claim not in system.content and claim in user.content for claim, _ in PAIRS)


async def test_unparsable_faithfulness() -> None:
    assert await judge.judge_faithfulness(FakeLLM(["all of them"]), "q", PAIRS) is None


def test_faithfulness_needs_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", "bm25", "bm25-wide", "--out", str(out)]) == 0
    with_report, _ = replay.read_results(out / "results.jsonl")
    run_dir = Path(with_report.run_dir or "")
    found = judge.context(run_dir)
    assert found is not None
    first = found.passages[0].n
    (run_dir / "report.json").write_text(report(f"Claim [{first}].").model_dump_json(), encoding="utf-8")
    llm = FakeLLM(["[0]", "[0]", "[0]"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    judged, without = judge.read_judgements(out / "judgements.jsonl")
    assert (judged.citations, judged.faithfulness) == (1, 1.0)
    assert (without.citations, without.faithfulness) == (0, None)
    assert judged.precision is not None
    assert without.precision is not None

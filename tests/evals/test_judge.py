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

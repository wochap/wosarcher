"""Judged precision with the fake LLM: parsing, message separation, and stored judgements."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

import evals.judge as judge
import evals.replay as replay
import wosarcher.build as building
from tests.evals.helpers import eval_env
from tests.runner.helpers import adapters
from wosarcher.adapters.fakes import FakeLLM
from wosarcher.adapters.llm import ChatLLM
from wosarcher.config import LLMConfig, Settings
from wosarcher.http import ProviderClient, ProviderError, UsageLedger
from wosarcher.models import Completion, Context, Effort, Message, Passage, Report
from wosarcher.ports import Adapters

PASSAGES = ["Lithium is recovered.", "Unrelated {text} with $query and <data>.", "Cobalt prices.", "Weather."]


def test_parse_yes_no() -> None:
    assert judge.parse_yes_no("yes") == 1.0
    assert judge.parse_yes_no("No.") == 0.0
    assert judge.parse_yes_no("Yes, because it names lithium") == 1.0
    assert judge.parse_yes_no("unclear") is None
    assert judge.parse_yes_no("") is None


async def test_precision() -> None:
    llm = FakeLLM(["yes", "no", "yes", "no"])
    assert await judge.judge_result(llm, "battery recycling", PASSAGES) == (0.5, 0)
    assert set(llm.efforts) == {"none"}
    assert set(llm.temperatures) == {0}


async def test_unparsable_answer() -> None:
    llm = FakeLLM(["yes", "I cannot tell", "yes", "yes"])
    assert await judge.judge_result(llm, "battery recycling", PASSAGES) == (1.0, 1)


async def test_all_unreadable() -> None:
    assert await judge.judge_result(FakeLLM(["maybe"]), "battery recycling", PASSAGES) == (None, 4)


async def test_samples_averaged() -> None:
    values = await judge.judge_items(FakeLLM(["yes", "yes", "no"]), "system", ["passage"], 3)
    assert [round(value or 0, 2) for value in values] == [0.67]


async def test_passages_in_separate_message() -> None:
    llm = FakeLLM(["no"])
    assert await judge.judge_result(llm, "battery recycling", PASSAGES) == (0.0, 0)
    for (system, user), text in zip(llm.calls, PASSAGES, strict=True):
        assert (system.role, user.role) == ("system", "user")
        assert "battery recycling" in system.content
        assert all(passage not in system.content for passage in PASSAGES)
        assert user.content == text


async def test_concurrent_calls() -> None:
    flight = {"now": 0, "peak": 0}
    bodies: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        flight["now"] += 1
        flight["peak"] = max(flight["peak"], flight["now"])
        await asyncio.sleep(0.01)
        flight["now"] -= 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "yes"}, "finish_reason": "stop"}]})

    cfg = LLMConfig.model_validate({"provider": "openai", "base_url": "http://llm.test/v1", "concurrency": 4})
    ledger = UsageLedger({})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ProviderClient(cfg.provider, cfg, http, ledger, backoff=0)
        llm = ChatLLM(cfg, client, ledger, "write")
        assert await judge.judge_result(llm, "q", [f"passage {n}" for n in range(30)]) == (1.0, 0)
    assert (len(bodies), flight["peak"]) == (30, 4)
    assert all(
        (body["reasoning_effort"], body["temperature"], body["max_completion_tokens"]) == ("none", 0, judge.MAX_TOKENS)
        for body in bodies
    )


def test_second_call_skips_judged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", "bm25", "--out", str(out)]) == 0
    llm = FakeLLM(["yes"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    calls = len(llm.calls)
    (judged,) = judge.read_judgements(out / "judgements.jsonl")
    assert judged.precision == 1.0
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    assert len(llm.calls) == calls


def test_force_rejudges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", "bm25", "bm25-wide", "--out", str(out)]) == 0
    llm = FakeLLM(["yes"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    llm.replies = ["no"]
    assert judge.main(["--results", str(out), "--profile", "e2e", "--force", "--samples", "2"]) == 0
    judged = judge.read_judgements(out / "judgements.jsonl")
    assert len(judged) == 2
    assert len({item.run_id for item in judged}) == 2
    assert all((item.precision, item.samples) == (0.0, 2) for item in judged)


def test_malformed_list_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", "bm25", "bm25-wide", "--out", str(out)]) == 0
    first_result, _ = replay.read_results(out / "results.jsonl")
    found = judge.context(Path(first_result.run_dir or ""))
    assert found is not None
    llm = FakeLLM(["[1, 2,]"] * len(found.passages) + ["yes"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    first, second = judge.read_judgements(out / "judgements.jsonl")
    assert (first.precision, first.unreadable) == (None, len(found.passages))
    assert second.precision == 1.0


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
    llm = FakeLLM(["yes", "no", "yes"])
    score, unreadable = await judge.judge_faithfulness(llm, "battery recycling", PAIRS)
    assert score is not None
    assert (round(score, 2), unreadable) == (0.67, 0)
    for (system, user), (claim, text) in zip(llm.calls, PAIRS, strict=True):
        assert "battery recycling" in system.content
        assert claim not in system.content
        assert claim in user.content
        assert text in user.content


async def test_unparsable_faithfulness() -> None:
    assert await judge.judge_faithfulness(FakeLLM(["all of them"]), "q", PAIRS) == (None, 3)


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
    llm = FakeLLM(["yes"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    judged, without = judge.read_judgements(out / "judgements.jsonl")
    assert (judged.citations, judged.faithfulness) == (1, 1.0)
    assert (without.citations, without.faithfulness) == (0, None)
    assert judged.precision is not None
    assert without.precision is not None


class FailingFirst(FakeLLM):
    """Raises a provider error on the first call, then replies like `FakeLLM`."""

    async def complete(
        self, messages: list[Message], *, max_tokens: int, effort: Effort, temperature: float | None = None
    ) -> Completion:
        if not self.calls:
            self.calls.append(list(messages))
            raise ProviderError("openai", "HTTP 502 at http://llm.test/v1/chat/completions: reasoning truncated")
        return await super().complete(messages, max_tokens=max_tokens, effort=effort, temperature=temperature)


def test_provider_error_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", "bm25", "bm25-wide", "--out", str(out)]) == 0
    llm = FailingFirst(["yes"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    first, second = judge.read_judgements(out / "judgements.jsonl")
    assert (first.precision, first.faithfulness) == (None, None)
    assert second.precision is not None
    assert set(llm.efforts) == {"none"}
    assert "HTTP 502" in capsys.readouterr().err

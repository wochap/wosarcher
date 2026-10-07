"""Judged metrics with the fake LLM: parsing, message separation, and stored judgements."""

import asyncio
import json
from pathlib import Path
from typing import Literal

import httpx
import pytest

import evals.items as evals_items
import evals.judge as judge
import evals.parts as evals_parts
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

TEXTS = ["Lithium is recovered.", "Unrelated {text} with $query and <data>.", "Cobalt prices.", "Weather."]
PASSAGES = list(enumerate(TEXTS, 1))


def test_parse_yes_no() -> None:
    assert judge.parse_yes_no("yes") == 1.0
    assert judge.parse_yes_no("No.") == 0.0
    assert judge.parse_yes_no("Yes, because it names lithium") == 1.0
    assert judge.parse_yes_no("unclear") is None
    assert judge.parse_yes_no("") is None


async def test_precision() -> None:
    llm = FakeLLM(["yes", "no", "yes", "no"])
    assert (await judge.judge_result(llm, "battery recycling", PASSAGES))[:2] == (0.5, 0)
    assert set(llm.efforts) == {"none"}
    assert set(llm.temperatures) == {0}


async def test_unparsable_answer() -> None:
    llm = FakeLLM(["yes", "I cannot tell", "yes", "yes"])
    assert (await judge.judge_result(llm, "battery recycling", PASSAGES))[:2] == (1.0, 1)


async def test_all_unreadable() -> None:
    assert (await judge.judge_result(FakeLLM(["maybe"]), "battery recycling", PASSAGES))[:2] == (None, 4)


async def test_samples_averaged() -> None:
    values, _ = await judge.judge_items(FakeLLM(["yes", "yes", "no"]), "system", ["passage"], 3)
    assert [round(value or 0, 2) for value in values] == [0.67]


async def test_passages_in_separate_message() -> None:
    llm = FakeLLM(["no"])
    assert (await judge.judge_result(llm, "battery recycling", PASSAGES))[:2] == (0.0, 0)
    for (system, user), text in zip(llm.calls, TEXTS, strict=True):
        assert (system.role, user.role) == ("system", "user")
        assert "battery recycling" in system.content
        assert all(passage not in system.content for passage in TEXTS)
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
        assert (await judge.judge_result(llm, "q", [(n, f"passage {n}") for n in range(30)]))[:2] == (1.0, 0)
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
    llm = FakeLLM(['["a"]'] + ["[1, 2,]"] * len(found.passages) + ["yes"])

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
        ("A is true [1]", 1, "passage 1"),
        ("B and C hold [2]", 2, "passage 2"),
        ("B and C hold [3]", 3, "passage 3"),
    ]
    assert judge.claims(report("See [1](https://example.com)."), passages(1)) == []


def claimed(body: str) -> list[str]:
    return [claim for claim, _, _ in judge.claims(report(body), passages(4))]


def test_claim_decimal_and_domain() -> None:
    body = "Hybrid reaches 0.7497 NDCG on gob.pe data [2], a 7.4% lift [3]."
    assert claimed(body) == [
        "Hybrid reaches 0.7497 NDCG on gob.pe data [2], a 7.4% lift",
        "Hybrid reaches 0.7497 NDCG on gob.pe data, a 7.4% lift [3]",
    ]


def test_claim_attributed_part_marked() -> None:
    body = "BM25 beats dense [2]; HyDE costs 40 ms [4]."
    assert claimed(body) == ["BM25 beats dense [2]; HyDE costs 40 ms", "BM25 beats dense; HyDE costs 40 ms [4]"]


def test_claim_adjacent_citations() -> None:
    assert claimed("Intro. Both say so [1][2].") == ["Both say so [1]", "Both say so [2]"]


def test_claim_list_item_and_table_row() -> None:
    body = "Prices:\n- **Costo:** gratuito [1]\n\n| Portal | Costo |\n|---|---|\n| CEJ | gratis [3] |\n"
    assert claimed(body) == ["Costo: gratuito [1]", "CEJ — Costo: gratis [3]"]


def test_claim_several_cited_cells() -> None:
    body = "| Tool | Role | License | Status |\n|---|---|---|---|\n| Jellyfin | Watch | GPL [3] | Active [4] |\n"
    assert claimed(body) == ["Jellyfin — License: GPL [3]", "Jellyfin — Status: Active [4]"]


def test_claim_table_without_header() -> None:
    assert claimed("| CEJ | gratis [3] |\n| Other | paid |\n") == ["CEJ — gratis [3]"]


def test_claim_line_break() -> None:
    assert claimed("# Heading\n\nThe CEJ changed\nits form in 2026 [4].") == ["The CEJ changed its form in 2026 [4]"]


PAIRS = [("A is true [1]", 1, "passage 1"), ("B and C hold [2]", 2, "passage 2"), ("B and C hold [3]", 3, "passage 3")]


async def test_faithfulness() -> None:
    llm = FakeLLM(["yes", "no", "yes"])
    score, unreadable, _ = await judge.judge_faithfulness(llm, "battery recycling", PAIRS)
    assert score is not None
    assert (round(score, 2), unreadable) == (0.67, 0)
    for (system, user), (claim, _, text) in zip(llm.calls, PAIRS, strict=True):
        assert "battery recycling" in system.content
        assert claim not in system.content
        assert claim in user.content
        assert text in user.content


async def test_whole_passage_sent() -> None:
    text = "x" * 1800
    llm = FakeLLM(["yes"])
    await judge.judge_result(llm, "q", [(1, text)])
    await judge.judge_faithfulness(llm, "q", [("A is true [1]", 1, text)])
    assert all(text in user.content for _, user in llm.calls)
    assert len(llm.calls) == 2


async def test_unparsable_faithfulness() -> None:
    assert (await judge.judge_faithfulness(FakeLLM(["all of them"]), "q", PAIRS))[:2] == (None, 3)


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


class FailingAt(FakeLLM):
    """Raises a provider error on call `at` (from 0), else replies like `FakeLLM`."""

    def __init__(self, replies: list[str], at: int) -> None:
        super().__init__(replies)
        self.at = at

    async def complete(
        self, messages: list[Message], *, max_tokens: int, effort: Effort, temperature: float | None = None
    ) -> Completion:
        if len(self.calls) == self.at:
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
    llm = FailingAt(['["a"]', "yes"], at=1)

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    first, second = judge.read_judgements(out / "judgements.jsonl")
    assert (first.precision, first.faithfulness, first.coverage, first.retrievable) == (None, None, None, None)
    assert second.precision is not None
    assert {item.run_id for item in judge.read_items(out / "items.jsonl")} == {second.run_id}
    assert set(llm.efforts) == {"none"}
    assert "HTTP 502" in capsys.readouterr().err


async def test_unreadable_item() -> None:
    _, _, (item,) = await judge.judge_result(FakeLLM(["unclear"]), "q", [(4, "passage")])
    assert (item.kind, item.n, item.value, item.answer) == ("precision", 4, None, "unclear")


def test_items_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", "bm25", "--out", str(out)]) == 0
    (result,) = replay.read_results(out / "results.jsonl")
    run_dir = Path(result.run_dir or "")
    found = judge.context(run_dir)
    assert found is not None
    first, second = found.passages[0].n, found.passages[1].n
    (run_dir / "report.json").write_text(report(f"A [{first}]. B [{second}].").model_dump_json(), encoding="utf-8")
    llm = FakeLLM(["yes"])

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    items = judge.read_items(out / "items.jsonl")
    kinds = [item.kind for item in items]
    assert (kinds.count("precision"), kinds.count("faithfulness")) == (len(found.passages), 2)
    assert {(item.run_id, item.variant) for item in items} == {(result.run_id, "bm25")}
    pairs = [item for item in items if item.kind == "faithfulness"]
    assert [(item.claim, item.n, item.value, item.answer) for item in pairs] == [
        (f"A [{first}]", first, 1.0, "yes"),
        (f"B [{second}]", second, 1.0, "yes"),
    ]
    assert all(item.short for item in pairs)
    assert pairs[0].passage == found.passages[0].text

    llm.replies = ["no"]
    assert judge.main(["--results", str(out), "--profile", "e2e", "--force"]) == 0
    again = judge.read_items(out / "items.jsonl")
    assert len(again) == len(items)
    assert all(item.value == 0.0 for item in again)


def judged_pair(index: int, value: float, claim: str) -> judge.JudgedItem:
    return judge.JudgedItem(
        run_id="r1",
        variant="bm25",
        kind="faithfulness",
        index=index,
        n=index + 1,
        claim=claim,
        passage=f"passage {index} " + "x" * 400,
        value=value,
        answer="yes",
    )


def test_items_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pairs = [judged_pair(index, 1.0, f"Fine {index}") for index in range(5)]
    pairs[1] = judged_pair(1, 0.0, "Wrong claim")
    judge.write_lines(tmp_path / "items.jsonl", pairs, "w")
    assert evals_items.main(["--results", str(tmp_path), "--failed"]) == 0
    shown = capsys.readouterr().out
    assert "bm25 · r1" in shown
    assert "Wrong claim" in shown
    assert "passage 1 " in shown
    assert "x" * 300 not in shown
    assert "Fine" not in shown
    assert evals_items.main(["--results", str(tmp_path / "missing")]) == 0
    assert capsys.readouterr().out == ""


def test_parts_parsed() -> None:
    assert evals_parts.parse_parts(json.dumps([f"part {i}" for i in range(26)])) == [f"part {i}" for i in range(20)]
    assert evals_parts.parse_parts('```json\n["a", " ", "b"]\n```') == ["a", "b"]
    assert evals_parts.parse_parts("The question asks about several things.") is None
    assert evals_parts.parse_parts('[""]') is None
    assert evals_parts.parse_parts('{"a": 1}') is None


PARTS = ["cost", "speed", "safety", "size"]


async def test_coverage() -> None:
    llm = FakeLLM(["yes", "no", "yes", "no"])
    coverage, unreadable, items = await judge.judge_coverage(llm, "q", PARTS, report("Body [1]."))
    assert (coverage, unreadable) == (0.5, 0)
    assert [(item.kind, item.n, item.part, item.passage) for item in items][1] == ("coverage", 2, "speed", "")


async def test_retrievable_from_passages() -> None:
    llm = FakeLLM(["yes"])
    await judge.judge_retrievable(llm, "battery recycling", ["cost"], PASSAGES[:3])
    ((system, user),) = llm.calls
    assert system.content == judge.Template(judge.RETRIEVABLE_PROMPT.read_text(encoding="utf-8")).substitute(
        query="battery recycling"
    )
    assert user.content.startswith("part: cost\npassages:\n")
    assert all(f"[{n}] {text}" in user.content for n, text in PASSAGES[:3])
    assert "report" not in user.content


def judged_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, llm: FakeLLM, *variants: str) -> Path:
    env, parent = eval_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "out"
    assert replay.main(["--runs", parent, "--variants", *variants, "--out", str(out)]) == 0

    def fake_build(settings: Settings, http: httpx.AsyncClient, ledger: UsageLedger) -> Adapters:
        return adapters(writer=llm)

    monkeypatch.setattr(building, "build", fake_build)
    return out


def parts_calls(llm: FakeLLM) -> int:
    return sum("JSON list" in messages[0].content for messages in llm.calls)


def test_parts_cached_per_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLLM(['["cost", "speed"]', "yes"])
    out = judged_env(tmp_path, monkeypatch, llm, "bm25", "bm25-wide")
    with_report, _ = replay.read_results(out / "results.jsonl")
    (Path(with_report.run_dir or "") / "report.json").write_text(report("Cost.").model_dump_json(), encoding="utf-8")
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    llm.replies = ["yes"]
    assert judge.main(["--results", str(out), "--profile", "e2e", "--force"]) == 0
    assert parts_calls(llm) == 1
    assert len(judge.lines(out / "parts.jsonl")) == 1
    judged, without = judge.read_judgements(out / "judgements.jsonl")
    assert (judged.parts, judged.coverage, judged.retrievable) == (2, 1.0, 1.0)
    assert (without.parts, without.coverage, without.retrievable) == (2, None, 1.0)
    items = [item for item in judge.read_items(out / "items.jsonl") if item.run_id == judged.run_id]
    kinds = [item.kind for item in items]
    assert (kinds.count("coverage"), kinds.count("retrievable")) == (2, 2)
    assert [(item.n, item.part, item.passage) for item in items if item.kind == "coverage"] == [
        (1, "cost", ""),
        (2, "speed", ""),
    ]
    coverage_calls = [messages for messages in llm.calls if messages[1:] and "report:" in messages[1].content]
    assert all(messages[1].content.endswith("report:\nCost.") for messages in coverage_calls)


def test_unparsable_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLLM(["The question asks about several things.", "yes"])
    out = judged_env(tmp_path, monkeypatch, llm, "bm25")
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    (judged,) = judge.read_judgements(out / "judgements.jsonl")
    assert (judged.parts, judged.coverage, judged.retrievable, judged.precision) == (0, None, None, 1.0)
    assert not (out / "parts.jsonl").exists()


def test_parts_provider_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FailingAt(["yes"], at=0)
    out = judged_env(tmp_path, monkeypatch, llm, "bm25")
    assert judge.main(["--results", str(out), "--profile", "e2e"]) == 0
    (judged,) = judge.read_judgements(out / "judgements.jsonl")
    assert (judged.parts, judged.retrievable, judged.precision) == (0, None, 1.0)
    assert not (out / "parts.jsonl").exists()


def test_failed_parts_listed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def part(kind: Literal["coverage", "retrievable"], value: float) -> judge.JudgedItem:
        return judge.JudgedItem(
            run_id="r1", variant="bm25", kind=kind, index=1, n=2, part="speed", value=value, answer="no"
        )

    judge.write_lines(tmp_path / "items.jsonl", [part("retrievable", 1.0), part("coverage", 0.0)], "w")
    assert evals_items.main(["--results", str(tmp_path), "--failed"]) == 0
    shown = capsys.readouterr().out
    assert "- coverage 0.00 part 2: speed" in shown
    assert "retrievable" not in shown

"""Catalog runs with fakes: waves, fetch per node, children, stop rules, resume, and costs."""

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.runner.helpers import adapters, kinds, settings
from tests.stages.catalog_data import structure, structure_data
from wosarcher.adapters.fakes import FakeFetcher, FakeLLM, FakeSearcher
from wosarcher.config import CatalogConfig, ReasoningConfig, Settings
from wosarcher.http import UsageLedger
from wosarcher.models import (
    CatalogDone,
    CatalogRecord,
    Completion,
    Context,
    Effort,
    Message,
    Node,
    NodeFailed,
    Report,
    RunFailed,
    RunRecord,
    RunRequest,
    Stage,
    StageDone,
    StageStarted,
    Structure,
    WaveDone,
)
from wosarcher.ports import Adapters
from wosarcher.runner import Runner
from wosarcher.store import RunStore

BRIEF = "Every public organization of the executive"
RELATION = "organismos adscritos"
SEARCH = {
    f"Poder Ejecutivo {RELATION}": ["https://pe.test/list"],
    "PCM ministry": ["https://pcm.test"],
    f"PCM {RELATION}": ["https://pcm.test/organismos"],
    "INEI agency": ["https://inei.test"],
}
PAGES = {
    "https://pe.test": "# Poder Ejecutivo\nThe executive.",
    "https://pe.test/list": "# Ministerios\nMEF, PCM.",
    "https://mef.test": "# MEF\nMinistry of economy.",
    "https://pcm.test": "# PCM\nPresidency.",
    "https://pcm.test/organismos": "# Organismos\nINEI.",
    "https://inei.test": "# INEI\nStatistics.",
}


def child(name: str, kind: str, url: str | None = None) -> dict[str, Any]:
    return {"name": name, "type": kind, "url": url}


CHILDREN: dict[str, list[dict[str, Any]]] = {
    "Poder Ejecutivo": [child("MEF", "ministry", "https://mef.test"), child("PCM", "ministry")],
    "PCM": [child("INEI", "agency")],
    "MEF": [child("INEI", "agency")],
}


def answer(name: str, children: Mapping[str, list[dict[str, Any]]] = CHILDREN) -> str:
    record = {"name": name, "website": None, "head_name": None, "verified_on": None}
    return json.dumps({"record": record, "sources": {}, "children": children.get(name, []), "flags": []})


class CatalogLLM(FakeLLM):
    """Extract replies by node name; any other call (the draft) gets `draft_reply`. Records usage per stage."""

    def __init__(
        self,
        reply: Callable[[str], str] = answer,
        draft_reply: str = "",
        ledger: UsageLedger | None = None,
        failing: set[str] | None = None,
    ) -> None:
        super().__init__()
        self.reply = reply
        self.draft_reply = draft_reply
        self.ledger = ledger
        self.failing = failing or set()
        self.names: list[str] = []
        self.levels: list[str] = []

    async def complete(
        self, messages: list[Message], *, max_tokens: int, effort: Effort, temperature: float | None = None
    ) -> Completion:
        self.calls.append(list(messages))
        system = messages[0].content
        self.levels.append(effort if "The entity: " in system else f"draft:{effort}")
        if "The entity: " not in system:
            if self.ledger:
                self.ledger.record("fake-llm", "draft", input_tokens=100, output_tokens=50)
            return Completion(text=self.draft_reply)
        name = system.split("The entity: ", 1)[1].split(" (type:", 1)[0]
        self.names.append(name)
        if self.ledger:
            self.ledger.record("fake-llm", "extract", input_tokens=10, output_tokens=5)
        if name in self.failing:
            raise RuntimeError("provider down")
        return Completion(text=self.reply(name))


def catalog_settings(tmp_path: Path, **catalog: Any) -> Settings:
    cfg = settings(tmp_path)
    return cfg.model_copy(update={"catalog": CatalogConfig.model_validate(catalog)})


def new_catalog(store: RunStore, cfg: Settings, found: Structure | None, until: Stage | None = None) -> str:
    request = RunRequest(query=BRIEF, sources="web", until=until, kind="catalog", structure=found)
    return store.create(request, "workstation", [], cfg, []).run_id


def world(
    tmp_path: Path,
    found: Structure | None = None,
    *,
    llm: CatalogLLM | None = None,
    search: Mapping[str, list[str]] = SEARCH,
    pages: Mapping[str, str] = PAGES,
    failing: set[str] | None = None,
    cfg: Settings | None = None,
    ledger: UsageLedger | None = None,
) -> tuple[RunStore, Runner, str, Adapters]:
    cfg = cfg or catalog_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    fakes = adapters(searcher=FakeSearcher(search), fetcher=FakeFetcher(pages, failing), planner=llm or CatalogLLM())
    runner = Runner(store, cfg, fakes, ledger or UsageLedger({}))
    run_id = new_catalog(store, cfg, structure(limits={"max_depth": 2}) if found is None else found)
    return store, runner, run_id, fakes


def nodes(store: RunStore, run_id: str) -> dict[str, Node]:
    return {node.id: node for node in store.read_items(run_id, "nodes.jsonl", Node)}


def catalog(store: RunStore, run_id: str) -> CatalogRecord:
    return store.read_artifact(run_id, "catalog.json", CatalogRecord)


async def test_three_waves(tmp_path: Path) -> None:
    store, runner, run_id, fakes = world(tmp_path)
    assert await runner.run(run_id) == "done"
    events = store.read_events(run_id)
    done = [(event.stage, event.data.round) for event in events if isinstance(event, StageDone)]
    assert done[:2] == [("load", 1), ("draft", 1)]
    assert done[2:7] == [(stage, 1) for stage in ("expand", "search", "fetch", "chunk", "extract")]
    assert done[7:12] == [(stage, 2) for stage in ("expand", "search", "fetch", "chunk", "extract")]
    assert done[-2:] == [("assemble", 1), ("write", 1)]
    assert {stage for stage, _ in done}.isdisjoint({"plan", "score", "select"})
    started = [event.data.round for event in events if isinstance(event, StageStarted) and event.stage == "fetch"]
    assert started == [1, 2, 3]
    waves = [event.data for event in events if isinstance(event, WaveDone)]
    assert [(w.wave, w.expanded, w.found, w.records) for w in waves] == [(1, 1, 2, 1), (2, 2, 1, 2), (3, 1, 0, 1)]
    found = nodes(store, run_id)
    assert list(found) == ["poder-ejecutivo", "mef", "pcm", "inei"]
    assert found["mef"].found_by == "links"
    assert found["pcm"].found_by == "search"
    assert found["inei"].parent_id == "mef"
    assert found["inei"].depth == 2
    assert found["inei"].flags == ["parent: also listed under PCM"]
    assert not found["inei"].expanded
    assert len(found["pcm"].pages) == 2
    result = catalog(store, run_id)
    assert [record["id"] for record in result.records] == ["poder-ejecutivo", "mef", "pcm", "inei"]
    assert result.records[3]["parent_id"] == "mef"
    assert result.records[3]["type"] == "agency"
    assert (result.reason, result.note) == ("frontier empty", "No unexpanded nodes left after wave 3.")
    done_event = next(event for event in events if isinstance(event, CatalogDone))
    assert (done_event.data.waves, done_event.data.records, done_event.data.flagged) == (3, 4, 1)
    names = {path.name for path in store.run_dir(run_id).iterdir()}
    expected = {"structure.json", "nodes.jsonl", "records.jsonl", "catalog.json", "plan.json", "hits.jsonl"}
    assert expected | {"pages.jsonl", "chunks.jsonl", "events.jsonl", "costs.json"} <= names
    assert names.isdisjoint({"report.md", "initial.jsonl", "scores.jsonl", "context.json"})
    started_event = events[0]
    assert started_event.type == "run.started"
    assert started_event.data.kind == "catalog"
    assert sorted(fakes.fetcher.calls) == sorted(set(fakes.fetcher.calls))  # type: ignore[attr-defined]


async def test_node_events(tmp_path: Path) -> None:
    store, runner, run_id, _ = world(tmp_path)
    await runner.run(run_id)
    types = kinds(store.read_events(run_id))
    assert types.count("structure.ready:draft") == 1
    assert types.count("node.found:draft") == 1
    assert types.count("node.found:extract") == 3
    assert types.count("node.extracted:extract") == 4
    assert "round.done:score" not in types


async def test_room_left_by_max_nodes(tmp_path: Path) -> None:
    many = {"Poder Ejecutivo": [child(f"Agency {n}", "agency") for n in range(6)]}
    llm = CatalogLLM(lambda name: answer(name, many))
    store, runner, run_id, _ = world(tmp_path, structure(limits={"max_nodes": 4}), llm=llm)
    await runner.run(run_id)
    assert len(nodes(store, run_id)) == 4
    waves = [event.data for event in store.read_events(run_id) if isinstance(event, WaveDone)]
    assert (waves[0].found, waves[0].dropped) == (3, 3)
    assert not nodes(store, run_id)["poder-ejecutivo"].expanded
    assert catalog(store, run_id).reason == "max nodes"


async def test_shared_page(tmp_path: Path) -> None:
    two = {"Poder Ejecutivo": [child("A", "office"), child("B", "office")]}
    search = {**SEARCH, "A office": ["https://shared.test"], "B office": ["https://shared.test"]}
    pages = {**PAGES, "https://shared.test": "# Shared\nBoth."}
    llm = CatalogLLM(lambda name: answer(name, two))
    store, runner, run_id, fakes = world(tmp_path, llm=llm, search=search, pages=pages)
    await runner.run(run_id)
    found = nodes(store, run_id)
    assert found["a"].pages == found["b"].pages
    assert fakes.fetcher.calls.count("https://shared.test") == 1  # type: ignore[attr-defined]


async def test_no_page(tmp_path: Path) -> None:
    store, runner, run_id, _ = world(tmp_path, failing={"https://mef.test"})
    assert await runner.run(run_id) == "done"
    mef = nodes(store, run_id)["mef"]
    assert (mef.status, mef.reason) == ("failed", "no page")
    failed = [event for event in store.read_events(run_id) if isinstance(event, NodeFailed)]
    assert [(event.stage, event.data.node_id) for event in failed] == [("fetch", "mef")]
    assert nodes(store, run_id)["pcm"].status == "extracted"


async def test_unknown_type(tmp_path: Path) -> None:
    odd = {"Poder Ejecutivo": [child("Programa X", "programa")]}
    store, runner, run_id, _ = world(tmp_path, llm=CatalogLLM(lambda name: answer(name, odd)))
    await runner.run(run_id)
    node = nodes(store, run_id)["programa-x"]
    assert node.type == "power"
    assert node.flags == ["type: programa not in the structure"]


async def test_too_many_children(tmp_path: Path) -> None:
    many = {"Poder Ejecutivo": [child(f"Agency {n}", "office") for n in range(5)]}
    cfg = catalog_settings(tmp_path, max_children=3)
    store, runner, run_id, _ = world(tmp_path, llm=CatalogLLM(lambda name: answer(name, many)), cfg=cfg)
    await runner.run(run_id)
    assert len(nodes(store, run_id)) == 4
    seed = catalog(store, run_id).records[0]
    assert "children: 2 beyond the limit dropped" in seed["flags"]


async def test_page_limit(tmp_path: Path) -> None:
    cfg = catalog_settings(tmp_path)
    cfg = cfg.model_copy(
        update={
            "fetch": cfg.fetch.model_copy(update={"max_pages": 2}),
            "chunk": cfg.chunk.model_copy(update={"min_chars": 0}),
        }
    )
    store, runner, run_id, _ = world(tmp_path, cfg=cfg)
    await runner.run(run_id)
    result = catalog(store, run_id)
    assert result.reason == "page limit reached"
    assert result.note.startswith("Page limit 2 reached.")
    assert len(result.waves) == 1


async def test_extract_failed(tmp_path: Path) -> None:
    llm = CatalogLLM(failing={"MEF", "PCM"})
    store, runner, run_id, _ = world(tmp_path, llm=llm)
    assert await runner.run(run_id) == "done"
    result = catalog(store, run_id)
    assert result.reason == "extract failed"
    assert result.note.startswith("Every extraction of wave 2 failed.")
    assert [record["id"] for record in result.records] == ["poder-ejecutivo"]
    assemble = next(e for e in store.read_events(run_id) if isinstance(e, StageDone) and e.stage == "assemble")
    assert assemble.data.warnings == ["extract failed: provider down"]


async def test_until_score_rejected(tmp_path: Path) -> None:
    store, runner, run_id, fakes = world(tmp_path)
    assert await runner.run(run_id, "score") == "failed"
    failed = next(e for e in store.read_events(run_id) if isinstance(e, RunFailed))
    assert "load, draft, expand, search, fetch, chunk, extract, assemble, write" in failed.data.error
    assert fakes.searcher.calls == []  # type: ignore[attr-defined]


async def test_derived_structure(tmp_path: Path) -> None:
    data = structure_data(limits={"max_depth": 1})
    llm = CatalogLLM(draft_reply=json.dumps(data))
    cfg = catalog_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    fakes = adapters(searcher=FakeSearcher(SEARCH), fetcher=FakeFetcher(PAGES), planner=llm)
    run_id = new_catalog(store, cfg, None)
    assert await Runner(store, cfg, fakes, UsageLedger({})).run(run_id) == "done"
    record = store.read_record(run_id)
    assert record.structure == store.read_artifact(run_id, "structure.json", Structure)
    assert record.structure is not None
    assert record.structure.limits.max_depth == 1


async def test_catalog_reasoning_levels(tmp_path: Path) -> None:
    base = catalog_settings(tmp_path)
    reasoning = ReasoningConfig(plan="high", gap="high", write="high", draft="medium", extract="low")
    cfg = base.model_copy(update={"llm": base.llm.model_copy(update={"reasoning": reasoning})})
    llm = CatalogLLM(draft_reply=json.dumps(structure_data(limits={"max_depth": 1})))
    store = RunStore.from_settings(cfg)
    fakes = adapters(searcher=FakeSearcher(SEARCH), fetcher=FakeFetcher(PAGES), planner=llm)
    run_id = new_catalog(store, cfg, None)
    assert await Runner(store, cfg, fakes, UsageLedger({})).run(run_id) == "done"
    assert llm.levels[0] == "draft:medium"
    assert len(llm.levels) > 1
    assert set(llm.levels[1:]) == {"low"}


async def test_unreadable_draft(tmp_path: Path) -> None:
    cfg = catalog_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    fakes = adapters(planner=CatalogLLM(draft_reply="nothing"))
    run_id = new_catalog(store, cfg, None)
    assert await Runner(store, cfg, fakes, UsageLedger({})).run(run_id) == "failed"
    failed = next(e for e in store.read_events(run_id) if isinstance(e, RunFailed))
    assert failed.data.stage == "draft"
    assert failed.data.error.startswith("draft failed:")


async def test_resume_after_interrupted_wave(tmp_path: Path) -> None:
    store, runner, run_id, _ = world(tmp_path)
    assert await runner.run(run_id, "fetch") == "done"
    # A second wave half-way: simulate by running wave 1 to the end, then interrupting wave 2 after fetch.
    store2, runner2, run_id2, _ = world(tmp_path / "b")
    llm = CatalogLLM()
    runner2.adapters = adapters(searcher=FakeSearcher(SEARCH), fetcher=FakeFetcher(PAGES), planner=llm)
    first = Interrupt(runner2, after=("fetch", 2))
    with pytest.raises(StopRunError):
        await first.run(run_id2)
    found = nodes(store2, run_id2)
    assert {node.id: node.status for node in found.values()} == {
        "poder-ejecutivo": "extracted",
        "mef": "expanding",
        "pcm": "expanding",
    }
    calls = len(llm.names)
    assert await runner2.run(run_id2) == "done"
    assert llm.names[calls:] == ["MEF", "PCM", "INEI"]
    result = catalog(store2, run_id2)
    assert [record["id"] for record in result.records] == ["poder-ejecutivo", "mef", "pcm", "inei"]
    assert [entry.wave for entry in result.waves] == [1, 2, 3]
    # The first run stopped inside wave 1 and resumes it.
    assert await runner.run(run_id) == "done"
    assert len(catalog(store, run_id).records) == 4


class StopRunError(Exception):
    pass


class Interrupt:
    """Runs a catalog run and raises `StopRunError` after a stage of a wave, like a killed process."""

    def __init__(self, runner: Runner, after: tuple[Stage, int]) -> None:
        self.runner = runner
        self.after = after

    async def run(self, run_id: str) -> None:
        original = self.runner.run_stage

        async def stage(ctx: Any, name: Stage, step: Any = None) -> None:
            await original(ctx, name, step)
            if (name, ctx.round.number) == self.after:
                raise StopRunError

        self.runner.run_stage = stage  # type: ignore[method-assign]
        try:
            await self.runner.run(run_id)
        finally:
            del self.runner.run_stage


async def test_cost_totals(tmp_path: Path) -> None:
    ledger = UsageLedger({})
    llm = CatalogLLM(draft_reply=json.dumps(structure_data(limits={"max_depth": 2})), ledger=ledger)
    cfg = catalog_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    fakes = adapters(searcher=FakeSearcher(SEARCH), fetcher=FakeFetcher(PAGES), planner=llm)
    run_id = new_catalog(store, cfg, None)
    await Runner(store, cfg, fakes, ledger).run(run_id)
    costs = store.read_costs(run_id)
    assert costs is not None
    assert costs.stages["draft"].requests == 1
    assert (costs.stages["extract"].requests, costs.stages["extract"].input_tokens) == (4, 40)
    assert costs.total.requests == 5


def test_record_kind(tmp_path: Path) -> None:
    cfg = catalog_settings(tmp_path)
    store = RunStore.from_settings(cfg)
    run_id = new_catalog(store, cfg, structure())
    record = RunRecord.model_validate_json((store.run_dir(run_id) / "request.json").read_text())
    assert (record.kind, record.request.depth) == ("catalog", None)
    assert record.structure == structure()


async def test_table_output_skips_write(tmp_path: Path) -> None:
    store, runner, run_id, _ = world(tmp_path)
    assert await runner.run(run_id) == "done"
    write = next(e for e in store.read_events(run_id) if isinstance(e, StageDone) and e.stage == "write")
    assert write.data.skipped
    run_dir = store.run_dir(run_id)
    assert not (run_dir / "report.md").exists()
    assert not (run_dir / "context.json").exists()
    assert catalog(store, run_id).output == "table"


async def test_both_output_writes_a_report(tmp_path: Path) -> None:
    store, runner, run_id, fakes = world(tmp_path, structure(limits={"max_depth": 2}, output="both"))
    assert await runner.run(run_id) == "done"
    events = store.read_events(run_id)
    write = next(e for e in events if isinstance(e, StageDone) and e.stage == "write")
    assert not write.data.skipped
    assert catalog(store, run_id).output == "both"
    context = store.read_artifact(run_id, "context.json", Context)
    assert [p.record_id for p in context.passages] == ["poder-ejecutivo", "mef", "pcm", "inei"]
    assert context.query == BRIEF
    report = store.read_artifact(run_id, "report.json", Report)
    assert report.records
    assert report.cited == [1]
    assert report.references[0].source_id == context.passages[0].source_id
    assert "## References" in (store.run_dir(run_id) / "report.md").read_text()
    writer = fakes.writer
    assert isinstance(writer, FakeLLM)
    user = writer.calls[0][-1].content
    assert "Poder Ejecutivo\npower" in user.split("<passages>", 1)[1]

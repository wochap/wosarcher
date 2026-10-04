import asyncio

from wosarcher.adapters.fakes import FakeManaged
from wosarcher.config import Settings
from wosarcher.doctor import check, exclusive_warnings
from wosarcher.models import ProviderHealth
from wosarcher.ports import Managed


def exclusive(**blocks: dict[str, object]) -> Settings:
    return Settings.model_validate({"run": {"gpu_policy": "exclusive"}, **blocks})


def row(block: str, **fields: object) -> FakeManaged:
    health = {"block": block, "provider": block, "status": "ok", "model": "m", "latency_ms": 5.0, **fields}
    return FakeManaged(ProviderHealth.model_validate(health))


def test_shared_device_without_release() -> None:
    settings = exclusive(
        score={"provider": "rerank", "device": "laptop:gpu0"},
        llm={"provider": "llm", "device": "laptop:gpu0", "release": "llama-swap"},
    )
    warnings = exclusive_warnings(settings)
    assert len(warnings) == 1
    assert warnings[0].startswith("score shares device laptop:gpu0")
    assert "llama-swap" in warnings[0]
    assert "ollama" in warnings[0]


def test_separate_devices_no_warning() -> None:
    settings = exclusive(
        score={"provider": "rerank", "device": "desktop:gpu0"},
        llm={"provider": "llm", "device": "laptop:gpu0"},
    )
    assert exclusive_warnings(settings) == []


def test_shared_policy_no_warning() -> None:
    settings = Settings.model_validate(
        {"score": {"provider": "rerank", "device": "gpu"}, "llm": {"provider": "llm", "device": "gpu"}}
    )
    assert exclusive_warnings(settings) == []


def remote() -> Settings:
    return Settings.model_validate({"prefilter": {"provider": "embeddings"}, "score": {"provider": "rerank"}})


def managed(**overrides: FakeManaged) -> dict[str, Managed]:
    rows: dict[str, Managed] = {name: row(name) for name in ("search", "fetch", "prefilter", "score", "llm")}
    rows.update(overrides)
    return rows


async def test_all_healthy() -> None:
    report = await check(remote(), managed())
    assert [health.block for health in report.providers] == ["search", "fetch", "prefilter", "score", "llm"]
    assert {health.status for health in report.providers} == {"ok"}
    assert report.warnings == ()


async def test_one_endpoint_down() -> None:
    down = row("score", status="failed", error="cannot connect to any endpoint: http://a/rerank, http://b/rerank")
    report = await check(remote(), managed(score=down))
    statuses = {health.block: health.status for health in report.providers}
    assert statuses == {"search": "ok", "fetch": "ok", "prefilter": "ok", "score": "failed", "llm": "ok"}


async def test_builtin_scorer_row() -> None:
    rows = managed()
    del rows["score"]
    settings = Settings.model_validate({"prefilter": {"provider": "embeddings"}, "score": {"provider": "bm25"}})
    report = await check(settings, rows)
    score = report.providers[3]
    assert (score.block, score.provider, score.status) == ("score", "bm25", "built-in")


async def test_release_unsupported_warns() -> None:
    settings = Settings.model_validate(
        {"score": {"provider": "rerank", "base_url": "http://d/v1", "release": "llama-swap"}}
    )
    report = await check(settings, managed(score=row("score", unload="no", base_url="http://d/v1")))
    assert report.warnings == ("score cannot unload: http://d/v1 does not answer like llama-swap",)


def window(size: int) -> Settings:
    return Settings.model_validate({"llm": {"provider": "llm", "context_window": size}})


async def test_context_too_small_warns() -> None:
    report = await check(window(32768), managed(llm=row("llm", context_window=4096)))
    assert len(report.warnings) == 1
    assert "4096" in report.warnings[0]
    assert "32768" in report.warnings[0]


async def test_context_large_enough_no_warning() -> None:
    report = await check(window(16384), managed(llm=row("llm", context_window=32768)))
    assert report.warnings == ()


async def test_no_context_no_warning() -> None:
    assert (await check(window(32768), managed())).warnings == ()


class Recorder(FakeManaged):
    """Records probe start, probe end, and release, in order, into a shared log."""

    def __init__(self, block: str, log: list[str], **fields: object) -> None:
        super().__init__(row(block, **fields).health)
        self.block, self.log = block, log

    async def probe(self) -> ProviderHealth:
        self.log.append(f"start {self.block}")
        await asyncio.sleep(0.01)
        self.log.append(f"end {self.block}")
        return self.health

    async def release(self) -> None:
        self.log.append(f"release {self.block}")


def local_pair(policy: str, release: str) -> Settings:
    device = {"device": "desktop:gpu0", "release": release}
    return Settings.model_validate(
        {"run": {"gpu_policy": policy}, "score": {"provider": "rerank", **device}, "llm": {"provider": "llm", **device}}
    )


async def test_local_probes_one_at_a_time() -> None:
    log: list[str] = []
    fakes: dict[str, Managed] = {name: Recorder(name, log) for name in ("search", "score", "llm")}
    await check(local_pair("shared", "none"), fakes)
    assert log.index("start llm") > log.index("end score")
    assert log.index("start search") < log.index("end score")


async def test_exclusive_policy_releases_between_local_probes() -> None:
    log: list[str] = []
    fakes: dict[str, Managed] = {name: Recorder(name, log, unload="yes") for name in ("score", "llm")}
    await check(local_pair("exclusive", "llama-swap"), fakes)
    assert log == ["start score", "end score", "release score", "start llm", "end llm"]


async def test_chosen_blocks_only() -> None:
    fakes = managed()
    report = await check(remote(), fakes, ["score"])
    assert [health.block for health in report.providers] == ["score"]

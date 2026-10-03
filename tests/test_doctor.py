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

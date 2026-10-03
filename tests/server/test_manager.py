from datetime import UTC, datetime
from pathlib import Path

import pytest

from wosarcher.config import parse_value
from wosarcher.models import (
    Attachment,
    ForkCreate,
    RunCreate,
    RunRecord,
    RunRequest,
    ServerSettings,
    WritingOptions,
    WritingPatch,
)
from wosarcher.server import staging
from wosarcher.server.staging import StagingError

CMD = ["wosarcher"]


def record(run_id: str = "orig", **fields: object) -> RunRecord:
    base: dict[str, object] = {
        "run_id": run_id,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "request": RunRequest(query="q", sources="files", until="select", attachments=["notes.md"]),
        "profile": "cloud",
        "overrides": ["score.top_k=5", 'write.tone="critical"'],
        "settings": {"write": {"tone": "critical"}},
    }
    return RunRecord.model_validate(base | fields)


def sets(argv: list[str]) -> list[str]:
    return [argv[n + 1] for n, flag in enumerate(argv) if flag == "--set"]


def test_stage_basename(tmp_path: Path) -> None:
    upload = Attachment(name="../../etc/notes.md", data=b"x")
    staged = staging.stage_run(tmp_path, RunCreate(query="q"), [upload], ServerSettings(), "workstation")
    path = staging.staging_dir(tmp_path, staged.run_id)
    assert (path / "attachments" / "notes.md").read_bytes() == b"x"
    assert staging.read_staged(tmp_path) == [staged]


def test_duplicate_names_rejected(tmp_path: Path) -> None:
    uploads = [Attachment(name="a/notes.md", data=b"1"), Attachment(name="b/notes.md", data=b"2")]
    with pytest.raises(StagingError, match=r"notes\.md"):
        staging.stage_run(tmp_path, RunCreate(query="q"), uploads, ServerSettings(), "workstation")
    assert not list(staging.queue_dir(tmp_path).glob("*"))


def test_argv_precedence(tmp_path: Path) -> None:
    defaults = ServerSettings(writing=WritingOptions(tone="formal", words=600), sources="web")
    request = RunCreate(query="q", writing=WritingPatch(tone="dry wit"), set=['write.tone="critical"', "a.b=1"])
    staged = staging.stage_run(tmp_path, request, [], defaults, "workstation")
    argv = staging.build_argv(CMD, staged, tmp_path)
    assert argv[:6] == ["wosarcher", "run", "q", "--run-id", staged.run_id, "--sources"]
    assert argv[6] == "web"
    flags = sets(argv)
    assert 'write.tone="dry wit"' in flags
    assert "write.words=600" in flags
    assert flags[-2:] == ['write.tone="critical"', "a.b=1"]
    assert parse_value(flags[flags.index('write.tone="dry wit"')].partition("=")[2]) == "dry wit"
    assert staged.writing_options.tone == "dry wit"


def test_fork_argv_profile(tmp_path: Path) -> None:
    fork = ForkCreate(from_stage="write", writing=WritingPatch(tone="critical"), profile="cloud")
    staged = staging.stage_fork(tmp_path, record(), fork)
    argv = staging.build_argv(CMD, staged, tmp_path)
    assert argv[:9] == ["wosarcher", "fork", "orig", "--from", "write", "--run-id", staged.run_id, "--profile", "cloud"]
    assert sets(argv) == ['write.tone="critical"']
    assert (staged.version, staged.parent, staged.from_stage) == (2, "orig", "write")


def test_rerun_staging_copies_attachments(tmp_path: Path) -> None:
    (tmp_path / "orig" / "attachments" / "dir").mkdir(parents=True)
    (tmp_path / "orig" / "attachments" / "notes.md").write_text("n")
    (tmp_path / "orig" / "attachments" / "dir" / "a.md").write_text("a")
    staged = staging.stage_rerun(tmp_path, record())
    copy = staging.staging_dir(tmp_path, staged.run_id) / "attachments"
    assert (copy / "notes.md").read_text() == "n"
    assert (copy / "dir" / "a.md").read_text() == "a"
    assert staged.kind == "rerun"
    assert staged.set == ["score.top_k=5", 'write.tone="critical"']


def test_rerun_argv_uses_saved_overrides(tmp_path: Path) -> None:
    (tmp_path / "orig" / "attachments").mkdir(parents=True)
    (tmp_path / "orig" / "attachments" / "notes.md").write_text("n")
    staged = staging.stage_rerun(tmp_path, record())
    argv = staging.build_argv(CMD, staged, tmp_path)
    copy = staging.staging_dir(tmp_path, staged.run_id) / "attachments" / "notes.md"
    assert argv[argv.index("--attach") + 1] == str(copy)
    assert argv[argv.index("--sources") + 1] == "files"
    assert argv[argv.index("--until") + 1] == "select"
    assert argv[argv.index("--profile") + 1] == "cloud"
    assert sets(argv) == ["score.top_k=5", 'write.tone="critical"']

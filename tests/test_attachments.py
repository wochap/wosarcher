from pathlib import Path

import pytest

from wosarcher.attachments import AttachmentError, collect


def write(path: Path, text: str = "text") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_mixed_directory(tmp_path: Path) -> None:
    for name in ("a.md", "b.txt", "c.pdf"):
        write(tmp_path / "docs" / name)
    attachments, skipped = collect([str(tmp_path / "docs")], max_bytes=1000)
    assert [Path(a.name).name for a in attachments] == ["a.md", "b.txt"]
    assert len(skipped) == 1
    assert skipped[0].item.endswith("c.pdf")
    assert "only .md and .txt" in skipped[0].reason


def test_oversized_file(tmp_path: Path) -> None:
    big = write(tmp_path / "big.md", "x" * 20)
    attachments, skipped = collect([str(big)], max_bytes=10)
    assert attachments == []
    assert skipped[0].item.endswith("big.md")
    assert skipped[0].reason == "larger than 10 bytes"


def test_nothing_matches(tmp_path: Path) -> None:
    pattern = str(tmp_path / "missing" / "*.md")
    with pytest.raises(AttachmentError, match="missing"):
        collect([pattern], max_bytes=1000)


def test_hidden_directory_ignored(tmp_path: Path) -> None:
    write(tmp_path / "docs" / "a.md")
    write(tmp_path / "docs" / ".git" / "b.md")
    write(tmp_path / "docs" / ".hidden.md")
    attachments, _ = collect([str(tmp_path / "docs")], max_bytes=1000)
    assert [Path(a.name).name for a in attachments] == ["a.md"]


def test_glob_and_same_file_twice(tmp_path: Path) -> None:
    file = write(tmp_path / "notes" / "a.md", "# A")
    attachments, _ = collect([str(tmp_path / "notes" / "*.md"), str(file)], max_bytes=1000)
    assert [a.data for a in attachments] == [b"# A"]

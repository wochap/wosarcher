"""Expand `--attach` paths (files, directories, globs) and read the files' bytes.

The only file I/O for attachments; `stages/load.py` works on the bytes.
"""

import glob
from collections.abc import Sequence
from pathlib import Path

from wosarcher.models import Attachment, Skipped

SUFFIXES = {".md", ".txt"}


class AttachmentError(Exception):
    pass


def expand(path: str) -> list[Path]:
    """Files named by one path: the file, a sorted recursive walk skipping hidden parts, or glob matches."""
    given = Path(path)
    if given.is_file():
        return [given]
    if given.is_dir():
        return [
            found
            for found in sorted(given.rglob("*"))
            if found.is_file() and not any(part.startswith(".") for part in found.relative_to(given).parts)
        ]
    matches = [Path(match) for match in sorted(glob.glob(path, recursive=True))]
    return [match for match in matches if match.is_file()]


def display(path: Path) -> str:
    """The path relative to the working directory where possible."""
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def collect(paths: Sequence[str], *, max_bytes: int) -> tuple[list[Attachment], list[Skipped]]:
    attachments: list[Attachment] = []
    skipped: list[Skipped] = []
    seen: set[Path] = set()
    for path in paths:
        files = expand(path)
        if not files:
            raise AttachmentError(f"--attach {path}: no file matches")
        for file in files:
            resolved = file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            name = display(file)
            if file.suffix.lower() not in SUFFIXES:
                skipped.append(Skipped(item=name, reason="unsupported file type (only .md and .txt)"))
            elif file.stat().st_size > max_bytes:
                skipped.append(Skipped(item=name, reason=f"larger than {max_bytes} bytes"))
            else:
                attachments.append(Attachment(name=name, data=file.read_bytes()))
    return attachments, skipped

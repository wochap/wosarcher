# Spec Delta

## Purpose

Keeps the ports-and-adapters layering of `src/wosarcher` enforced by an
automated, tested gate that `scripts/check` runs, so a layering violation
fails the sanity check instead of reaching review.

## ADDED Requirements

### Requirement: Allowed internal imports
`scripts/check_architecture.py` SHALL fail, naming the file, line, importing
part, and imported part, when a top-level part of `src/wosarcher` (a module
or a subpackage) imports an internal part that is not listed for it in its
allow table. Every import form SHALL count: `import wosarcher.x`,
`from wosarcher.x import y`, `from wosarcher import x`, and relative
imports. A part that is missing from the allow table SHALL fail with a
message that says to add it.

#### Scenario: Stage imports the store
- **WHEN** a module under `stages/` contains `from wosarcher.store import RunStore`
- **THEN** the check fails naming that file and line, `stages`, and `store`

#### Scenario: Package-level import form
- **WHEN** a module under `stages/` contains `from wosarcher import adapters`
- **THEN** the check fails naming `stages` and `adapters`

### Requirement: Adapters are independent
No module under `adapters/`, including `adapters/__init__.py`, SHALL import
another adapter module, in any import form. An adapter module MAY import
itself and the shared parts its allow table lists.

#### Scenario: Import through the package
- **WHEN** `adapters/llm.py` contains `from wosarcher.adapters import bm25`
- **THEN** the check fails naming adapter `llm` and adapter `bm25`

#### Scenario: Relative import
- **WHEN** `adapters/llm.py` contains `from .bm25 import BM25Scorer`
- **THEN** the check fails naming adapter `llm` and adapter `bm25`

#### Scenario: Package registry
- **WHEN** `adapters/__init__.py` contains `from wosarcher.adapters import searxng`
- **THEN** the check fails naming `adapters/__init__.py`

### Requirement: Pure parts do no I/O
The pure parts (`models`, `ports`, `lexical`, `stages`, `prompts`) SHALL
NOT import interface or I/O libraries (`httpx`, `fastapi`, `starlette`,
`uvicorn`, `typer`, `rich`, `respx`, `requests`, `aiohttp`) or the standard
library's file, process, and network modules (`os`, `io`, `subprocess`,
`socket`, `shutil`, `tempfile`, `sqlite3`, `urllib.request`,
`http.client`, `importlib`), SHALL NOT import `Path` from `pathlib`, and
SHALL NOT call the `open` builtin or `__import__`. `importlib.resources`
SHALL be allowed in `prompts` only, which reads its own package data. Pure
path classes (`PurePath`, `PurePosixPath`, `PureWindowsPath`) and
`urllib.parse` SHALL stay allowed.

#### Scenario: Stage opens a file
- **WHEN** a module under `stages/` calls `open("x.txt")`
- **THEN** the check fails naming that file and line and the `open` builtin

#### Scenario: Stage imports subprocess
- **WHEN** a module under `stages/` contains `import subprocess`
- **THEN** the check fails naming `stages` and `subprocess`

#### Scenario: Pure path allowed
- **WHEN** a module under `stages/` contains `from pathlib import PurePosixPath`
- **THEN** the check reports no violation for that line

#### Scenario: Prompts read package data
- **WHEN** `prompts/__init__.py` contains `from importlib.resources import files`
- **THEN** the check reports no violation, while the same line in a module under `stages/` fails

### Requirement: The gate is tested
The architecture check SHALL run against a package directory given to it,
and an automated test SHALL run it against small generated packages that
each contain one violation from this specification, and against a clean
package, and SHALL assert the exact violations reported. The check SHALL
report no violation for the current `src/wosarcher` tree.

#### Scenario: Clean tree
- **WHEN** `scripts/check` runs on the repository
- **THEN** the architecture step prints `architecture: ok`

#### Scenario: Injected violation
- **WHEN** the test writes a generated package whose `adapters/llm.py` imports `wosarcher.adapters.bm25`
- **THEN** the check returns exactly one violation, naming `llm` and `bm25`

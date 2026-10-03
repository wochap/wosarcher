"""Check that src/wosarcher follows the ports-and-adapters layering.

Each top-level part of the package (a module or a subpackage) may import
only the parts listed for it in ALLOWED. Pure parts may not import
I/O or interface libraries. Adapters may not import each other.

Standard library only, so it runs before `uv sync`. Exit code 1 on any
violation. See docs/design.md, "Architecture".
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PACKAGE = "wosarcher"
ROOT = Path(__file__).resolve().parent.parent / "src" / PACKAGE

# Internal parts each part may import. A part may always import itself.
ALLOWED: dict[str, set[str]] = {
    "__init__": set(),
    "models": set(),
    "ports": {"models"},
    "lexical": {"models"},
    "config": {"models"},
    "http": {"models", "config"},
    "store": {"models", "config"},
    # Prompt files are read-only package data; stages own their prompts, so they load them.
    "prompts": set(),
    # Attachment paths come from the user and must be read from disk outside the pure stages.
    "attachments": {"models", "config"},
    "stages": {"models", "ports", "lexical", "config", "prompts"},
    "adapters": {"models", "ports", "lexical", "config", "http"},
    # The health check is shared by the CLI and, later, `GET /providers/health`.
    "doctor": {"models", "ports", "config"},
    "runner": {"models", "ports", "lexical", "config", "http", "stages", "store", "prompts", "attachments"},
    "build": {
        "models",
        "ports",
        "lexical",
        "config",
        "http",
        "stages",
        "store",
        "adapters",
        "runner",
        "prompts",
        "attachments",
    },
    "server": {
        "models",
        "ports",
        "lexical",
        "config",
        "http",
        "stages",
        "store",
        "adapters",
        "runner",
        "build",
        "doctor",
        "prompts",
        "attachments",
    },
    "cli": {
        "models",
        "ports",
        "lexical",
        "config",
        "http",
        "stages",
        "store",
        "adapters",
        "runner",
        "build",
        "doctor",
        "server",
        "prompts",
        "attachments",
    },
    "__main__": {"cli"},
}

# Parts that must stay free of I/O and interface libraries.
PURE = {"models", "ports", "lexical", "stages", "prompts"}
IO_LIBRARIES = {"httpx", "fastapi", "starlette", "uvicorn", "typer", "rich", "respx"}


def part_of(path: Path) -> str:
    """The top-level part a file belongs to: `stages/plan.py` -> `stages`."""
    relative = path.relative_to(ROOT)
    return relative.parts[0].removesuffix(".py")


def module_name(path: Path) -> list[str]:
    """Dotted module path as a list: `stages/plan.py` -> [wosarcher, stages, plan]."""
    relative = path.relative_to(ROOT).with_suffix("")
    parts = [PACKAGE, *relative.parts]
    return parts[:-1] if parts[-1] == "__init__" else parts


def imported_modules(path: Path, tree: ast.Module) -> list[tuple[int, str]]:
    """Absolute names of every module the file imports, with line numbers."""
    is_package = path.name == "__init__.py"
    current = module_name(path)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                package = current if is_package else current[:-1]
                anchor = package[: len(package) - (node.level - 1)]
                base = ".".join([*anchor, *([node.module] if node.module else [])])
            if node.module is None and node.level > 0:
                # `from . import x` imports submodules x of the anchor package.
                found.extend((node.lineno, f"{base}.{alias.name}") for alias in node.names)
            else:
                found.append((node.lineno, base))
    return found


def check_file(path: Path) -> list[str]:
    part = part_of(path)
    where = path.relative_to(ROOT.parent.parent)
    if part not in ALLOWED:
        return [
            f"{where}: '{part}' is not in ALLOWED in scripts/check_architecture.py; add it with its allowed imports"
        ]

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    errors: list[str] = []
    for line, name in imported_modules(path, tree):
        top = name.split(".")[0]
        if top == PACKAGE:
            target = name.split(".")[1] if "." in name else "__init__"
            if target == part:
                if part == "adapters":
                    errors.extend(check_adapter_independence(path, line, name, where))
                continue
            if target not in ALLOWED[part]:
                errors.append(f"{where}:{line}: '{part}' must not import '{target}' ({name})")
        elif part in PURE and top in IO_LIBRARIES:
            errors.append(f"{where}:{line}: '{part}' is pure and must not import '{top}'")
    return errors


def check_adapter_independence(path: Path, line: int, name: str, where: Path) -> list[str]:
    """An adapter module may not import another adapter module."""
    own = path.relative_to(ROOT / "adapters").with_suffix("").parts
    if not own or own[0] == "__init__":
        return []
    parts = name.split(".")
    if len(parts) < 3:
        return []
    other = parts[2]
    if other != own[0]:
        return [f"{where}:{line}: adapter '{own[0]}' must not import adapter '{other}'"]
    return []


def main() -> int:
    if not ROOT.is_dir():
        print(f"architecture: skipped ({ROOT.relative_to(ROOT.parent.parent)} does not exist)")
        return 0
    errors = [error for path in sorted(ROOT.rglob("*.py")) for error in check_file(path)]
    for error in errors:
        print(error)
    if errors:
        print(f"architecture: {len(errors)} violation(s)")
        return 1
    print("architecture: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
    # Builds the Markdown that report export converts.
    "document": {"models"},
    "config": {"models"},
    "http": {"models", "config"},
    "store": {"models", "config"},
    # Password, token, and session handling is shared by the CLI and the server without FastAPI.
    "auth": {"config"},
    # Prompt files are read-only package data; stages own their prompts, so they load them.
    "prompts": set(),
    # Attachment paths come from the user and must be read from disk outside the pure stages.
    "attachments": {"models", "config"},
    "stages": {"models", "ports", "lexical", "config", "prompts"},
    "adapters": {"models", "ports", "lexical", "config", "http"},
    # The health check is shared by the CLI and, later, `GET /providers/health`.
    "doctor": {"models", "ports", "config"},
    "runner": {"models", "ports", "lexical", "config", "http", "stages", "store", "prompts", "attachments", "doctor"},
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
        "auth",
        "document",
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
        "auth",
        "document",
    },
    "__main__": {"cli"},
}

# Parts that must stay free of I/O and interface libraries.
PURE = {"models", "ports", "lexical", "document", "stages", "prompts"}
# Module prefixes pure parts may not import: `urllib.request` is caught, `urllib.parse` is not.
PURE_FORBIDDEN = {
    "httpx",
    "fastapi",
    "starlette",
    "uvicorn",
    "typer",
    "rich",
    "respx",
    "requests",
    "aiohttp",
    "os",
    "io",
    "subprocess",
    "socket",
    "shutil",
    "tempfile",
    "sqlite3",
    "urllib.request",
    "http.client",
    "importlib",
}
# Prompt files are package data, read through importlib.resources.
PURE_EXCEPTIONS: dict[str, set[str]] = {"prompts": {"importlib.resources"}}
# Builtins that open files or load modules.
PURE_FORBIDDEN_CALLS = {"open", "__import__"}
PURE_PATH_CLASSES = {"PurePath", "PurePosixPath", "PureWindowsPath"}


def part_of(path: Path, root: Path) -> str:
    """The top-level part a file belongs to: `stages/plan.py` -> `stages`."""
    relative = path.relative_to(root)
    return relative.parts[0].removesuffix(".py")


def module_name(path: Path, root: Path) -> list[str]:
    """Dotted module path as a list: `stages/plan.py` -> [wosarcher, stages, plan]."""
    relative = path.relative_to(root).with_suffix("")
    parts = [PACKAGE, *relative.parts]
    return parts[:-1] if parts[-1] == "__init__" else parts


def imported_modules(path: Path, root: Path, tree: ast.Module) -> list[tuple[int, str]]:
    """Absolute names of every module the file imports, with line numbers.

    `from P import name` records both `P` and `P.name`, since `name` may be a submodule;
    `from wosarcher import name` records only `wosarcher.name`.
    """
    is_package = path.name == "__init__.py"
    current = module_name(path, root)
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
            if base != PACKAGE:
                found.append((node.lineno, base))
            found.extend((node.lineno, f"{base}.{alias.name}") for alias in node.names)
    return found


def forbidden_in_pure(part: str, name: str) -> str | None:
    """The forbidden prefix `name` falls under in a pure part, if any."""
    allowed = PURE_EXCEPTIONS.get(part, set())
    if any(name == prefix or name.startswith(prefix + ".") for prefix in allowed):
        return None
    for prefix in PURE_FORBIDDEN:
        if name == prefix or name.startswith(prefix + "."):
            return prefix
    return None


def check_file(path: Path, root: Path) -> list[str]:
    part = part_of(path, root)
    where = path.relative_to(root.parent.parent)
    if part not in ALLOWED:
        return [
            f"{where}: '{part}' is not in ALLOWED in scripts/check_architecture.py; add it with its allowed imports"
        ]

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    errors: list[str] = []
    seen: set[tuple[int, str]] = set()
    for line, name in imported_modules(path, root, tree):
        top = name.split(".")[0]
        if top == PACKAGE:
            target = name.split(".")[1] if "." in name else "__init__"
            if target == part:
                if part == "adapters":
                    error = adapter_independence(path, root, line, name, where)
                    if error and (line, error) not in seen:
                        seen.add((line, error))
                        errors.append(error)
                continue
            if target not in ALLOWED[part] and (line, target) not in seen:
                seen.add((line, target))
                errors.append(f"{where}:{line}: '{part}' must not import '{target}' ({name})")
        elif part in PURE:
            prefix = forbidden_in_pure(part, name)
            if prefix and (line, prefix) not in seen:
                seen.add((line, prefix))
                errors.append(f"{where}:{line}: '{part}' is pure and must not import '{prefix}'")
    if part in PURE:
        errors.extend(pure_names(part, tree, where))
    return errors


def pure_names(part: str, tree: ast.Module, where: Path) -> list[str]:
    """Concrete `pathlib` paths and calls to the `open` and `__import__` builtins."""
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "pathlib" for alias in node.names):
            errors.append(
                f"{where}:{node.lineno}: '{part}' is pure and must not import 'pathlib'; use a pure path class"
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "pathlib":
            errors.extend(
                f"{where}:{node.lineno}: '{part}' is pure and must not import 'pathlib.{alias.name}'"
                for alias in node.names
                if alias.name not in PURE_PATH_CLASSES
            )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in PURE_FORBIDDEN_CALLS:
            errors.append(f"{where}:{node.lineno}: '{part}' is pure and must not call '{node.func.id}'")
    return errors


def adapter_independence(path: Path, root: Path, line: int, name: str, where: Path) -> str | None:
    """An adapter module, `adapters/__init__.py` included, may not import another adapter module."""
    own = path.relative_to(root / "adapters").with_suffix("").parts[0]
    parts = name.split(".")
    if len(parts) < 3 or parts[2] == own:
        return None
    return f"{where}:{line}: adapter '{own}' must not import adapter '{parts[2]}'"


def check_tree(root: Path) -> list[str]:
    """Every violation in the package at `root`."""
    return [error for path in sorted(root.rglob("*.py")) for error in check_file(path, root)]


def main() -> int:
    if not ROOT.is_dir():
        print(f"architecture: skipped ({ROOT.relative_to(ROOT.parent.parent)} does not exist)")
        return 0
    errors = check_tree(ROOT)
    for error in errors:
        print(error)
    if errors:
        print(f"architecture: {len(errors)} violation(s)")
        return 1
    print("architecture: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

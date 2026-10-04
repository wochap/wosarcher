"""`scripts/check_architecture.py` reports exactly the layering violations it is meant to catch."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_architecture.py"
_spec = importlib.util.spec_from_file_location("check_architecture", SCRIPT)
assert _spec
assert _spec.loader
check = importlib.util.module_from_spec(_spec)
sys.modules["check_architecture"] = check
_spec.loader.exec_module(check)


def make_package(tmp_path: Path, files: dict[str, str]) -> Path:
    """A minimal `src/wosarcher` tree holding `files`, with an `__init__.py` per subpackage used."""
    root = tmp_path / "src" / "wosarcher"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent != root:
            (path.parent / "__init__.py").touch()
        path.write_text(text)
    return root


def violations(tmp_path: Path, files: dict[str, str]) -> list[str]:
    return check.check_tree(make_package(tmp_path, files))


def test_clean_package(tmp_path: Path) -> None:
    files = {
        "models.py": "from pydantic import BaseModel\n",
        "stages/plan.py": "import asyncio\nfrom urllib.parse import urlsplit\nfrom wosarcher.models import Chunk\n",
        "adapters/llm.py": "import httpx\nfrom wosarcher.http import Client\nfrom .llm import X\n",
        "prompts/__init__.py": "from importlib.resources import files\n",
    }
    assert violations(tmp_path, files) == []


def test_repository_tree_is_clean() -> None:
    assert check.check_tree(check.ROOT) == []


def test_stage_imports_store(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "\nfrom wosarcher.store import RunStore\n"})
    assert "src/wosarcher/stages/plan.py:2" in error
    assert "'stages'" in error
    assert "'store'" in error


def test_package_level_import(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "from wosarcher import adapters\n"})
    assert "'stages'" in error
    assert "'adapters'" in error


def test_adapter_imports_adapter_through_package(tmp_path: Path) -> None:
    files = {"adapters/llm.py": "from wosarcher.adapters import bm25\n", "adapters/bm25.py": ""}
    [error] = violations(tmp_path, files)
    assert "'llm'" in error
    assert "'bm25'" in error


def test_adapter_relative_import(tmp_path: Path) -> None:
    files = {"adapters/llm.py": "from .bm25 import BM25Scorer\n", "adapters/bm25.py": ""}
    [error] = violations(tmp_path, files)
    assert "'llm'" in error
    assert "'bm25'" in error


def test_adapters_init_registry(tmp_path: Path) -> None:
    files = {"adapters/__init__.py": "from wosarcher.adapters import searxng\n", "adapters/searxng.py": ""}
    [error] = violations(tmp_path, files)
    assert "adapters/__init__.py" in error
    assert "'searxng'" in error


def test_stage_open_builtin(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "\n\ntext = open('x.txt').read()\n"})
    assert "stages/plan.py:3" in error
    assert "'open'" in error


def test_stage_imports_subprocess(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "import subprocess\n"})
    assert "'stages'" in error
    assert "'subprocess'" in error


def test_stage_imports_urllib_request(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "from urllib.request import urlopen\n"})
    assert "'urllib.request'" in error


def test_stage_imports_pathlib_path(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "from pathlib import Path\n"})
    assert "pathlib.Path" in error


def test_stage_pure_path_allowed(tmp_path: Path) -> None:
    assert violations(tmp_path, {"stages/plan.py": "from pathlib import PurePosixPath\n"}) == []


def test_stage_urllib_parse_allowed(tmp_path: Path) -> None:
    assert violations(tmp_path, {"stages/plan.py": "import urllib.parse\n"}) == []


def test_prompts_importlib_resources_allowed(tmp_path: Path) -> None:
    assert violations(tmp_path, {"prompts/__init__.py": "from importlib.resources import files\n"}) == []


def test_stage_importlib_resources_forbidden(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "from importlib.resources import files\n"})
    assert "'importlib'" in error


def test_stage_dunder_import(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "os = __import__('os')\n"})
    assert "'__import__'" in error


def test_stage_imports_requests(tmp_path: Path) -> None:
    [error] = violations(tmp_path, {"stages/plan.py": "import requests\n"})
    assert "'requests'" in error

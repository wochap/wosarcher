"""Typing test: basedpyright must reject a fake with a wrong signature.

`reportUnnecessaryTypeIgnoreComment` turns the ignore below into an
assertion: if the assignment ever type-checks, basedpyright fails.
"""

from wosarcher.models import Hit
from wosarcher.ports import Searcher


class WrongSearcher:
    async def search(self, text: str, limit: int) -> list[Hit]:
        return []


wrong: Searcher = WrongSearcher()  # pyright: ignore[reportAssignmentType]


def test_fakes_module_imports() -> None:
    from wosarcher.adapters import fakes

    assert fakes.FakeScorer().name == "fake"

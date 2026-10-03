from string import Template

import pytest

from wosarcher.prompts import load


def test_load_plan() -> None:
    assert isinstance(load("plan"), Template)


def test_unknown_prompt_named() -> None:
    with pytest.raises(FileNotFoundError, match="missing-prompt"):
        load("missing-prompt")


def test_query_dollar_kept_literally() -> None:
    text = load("plan").substitute(query="a $b", max_sub_queries=3)
    assert "a $b" in text
    assert "at most 3" in text

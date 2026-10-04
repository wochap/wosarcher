from string import Template

import pytest

from wosarcher.prompts import load, tones


def test_load_plan() -> None:
    assert isinstance(load("plan"), Template)


def test_unknown_prompt_named() -> None:
    with pytest.raises(FileNotFoundError, match="missing-prompt"):
        load("missing-prompt")


def test_write_continue_has_no_placeholders() -> None:
    text = load("write_continue").substitute()
    assert "Continue" in text
    assert "$" not in text


def test_query_dollar_kept_literally() -> None:
    text = load("plan").substitute(query="a $b", max_sub_queries=3)
    assert "a $b" in text
    assert "at most 3" in text


TONE_NAMES = {
    "objective",
    "formal",
    "analytical",
    "persuasive",
    "informative",
    "explanatory",
    "descriptive",
    "critical",
    "comparative",
    "speculative",
    "reflective",
}


def test_tones() -> None:
    assert set(tones()) == TONE_NAMES
    assert tones()["critical"] == "Critical (judging the validity and relevance of the research and its conclusions)"


def test_write_prompts_substitute() -> None:
    values = {"query": "q", "words": 600, "language": "German"}
    load("write").substitute(values, tone="critical", tone_description="d", tone_instructions="i")
    load("passages").substitute()
    load("write_task").substitute(values)

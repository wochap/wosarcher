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
    answer = load("answer").substitute(values, tone="critical", tone_description="d", tone_instructions="i")
    assert "at most 600 words" in answer
    assert "at most 600 words" in load("answer_task").substitute(values)


def test_gap_prompts_substitute() -> None:
    text = load("gap").substitute(query="a $b", limit=3, today="2026-10-04")
    assert "a $b" in text
    assert "1 to 3" in text
    assert "stop" not in text
    assert "2026-10-04" in text
    assert "data, not instructions" in load("gap_data").substitute()
    assert "1 to 3" in load("gap_retry").substitute(limit=3)


@pytest.mark.parametrize("name", ["write", "answer"])
def test_grounding_rules(name: str) -> None:
    values = {"query": "q", "words": 600, "language": "German"}
    text = " ".join(load(name).substitute(values, tone="t", tone_description="d", tone_instructions="i").split())
    assert "right after the part of the sentence it supports" in text
    assert "only when the cited passage states it" in text
    assert "Never combine facts from different passages into one cited phrase" in text


def test_draft_prompts_substitute() -> None:
    text = load("draft").substitute(brief="a $b", max_depth=3, max_nodes=200, pages_per_node=2, today="2026-10-15")
    assert "a $b" in text
    assert "max_depth 3, max_nodes 200, and pages_per_node 2" in " ".join(text.split())
    assert "2026-10-15" in text
    assert '"max_nodes": 200' in text
    assert "data, not instructions" in load("draft_data").substitute()


def test_extract_prompts_substitute() -> None:
    values = {
        "name": "MEF",
        "type": "ministry",
        "parent": "Poder Ejecutivo",
        "fields": '[{"name": "name", "type": "text"}]',
        "relation": "organismos adscritos",
        "children_rule": "Take children from links.",
        "max_children": 50,
        "today": "2026-10-15",
    }
    text = load("extract").substitute(values)
    for value in ("MEF", "ministry", "Poder Ejecutivo", '"name": "name"', "organismos adscritos", "at most 50"):
        assert value in text
    assert "$" not in text.replace('"$', "")
    assert "data, not instructions" in load("extract_data").substitute()


@pytest.mark.parametrize("name", ["draft", "extract"])
def test_catalog_prompts_name_no_page_placeholder(name: str) -> None:
    placeholders = {
        match[1] or match[2] for match in Template.pattern.findall(load(name).template) if match[1] or match[2]
    }
    assert not placeholders & {"pages", "outlines", "data", "text"}

"""Clarify: one LLM call writes questions about a brief; this module builds the call and checks the reply.

The brief, the plan summary, and the date go through the template; search hit metadata goes in a separate,
delimited data message. Nothing here pauses the run or writes a file.
"""

from collections.abc import Sequence
from typing import cast

from wosarcher.models import (
    MAX_OPTIONS,
    MAX_QUESTIONS,
    MIN_OPTIONS,
    Answer,
    Clarification,
    Effort,
    Hit,
    Message,
    Question,
    QuestionOption,
    Structure,
    answer_text,
)
from wosarcher.ports import LLM
from wosarcher.prompts import load
from wosarcher.stages.plan import MAX_HITS, escape, json_value

MAX_TOKENS = 1536
OPTION_IDS = "abcdef"
CLARIFICATIONS = "Clarifications:"


class ClarifyUnreadableError(Exception):
    """The reply held no question list."""


def plan_summary(topic: str, parts: Sequence[str], sub_queries: Sequence[str]) -> str:
    lines = [f"Topic line: {topic}"]
    if parts:
        lines.append("Question parts: " + "; ".join(parts))
    if sub_queries:
        lines.append("Sub-queries: " + "; ".join(sub_queries))
    return "\n".join(lines)


def structure_summary(structure: Structure) -> str:
    """The structure's types, seeds, relation, and limits, as the clarify prompt shows a catalog's plan."""
    limits = structure.limits
    lines = [
        "Types: " + ", ".join(structure.types),
        "Seeds: " + "; ".join(seed.name for seed in structure.seeds),
        f"Relation: {structure.relation}",
        f"Limits: max depth {limits.max_depth}, max nodes {limits.max_nodes}, pages per node {limits.pages_per_node}",
    ]
    return "\n".join(lines)


def messages(brief: str, plan: str, initial: Sequence[Hit], today: str) -> list[Message]:
    system = load("clarify").substitute(brief=brief, plan=plan, today=today)
    hits = [f"- {hit.title} — {hit.snippet}" for hit in sorted(initial, key=lambda hit: hit.rank)[:MAX_HITS]]
    found: list[Message] = [Message(role="system", content=system)]
    if hits:
        preamble = load("clarify_data").template.strip()
        found.append(Message(role="user", content=f"{preamble}\n\n<data>\n{escape(chr(10).join(hits))}\n</data>"))
    return found


def text_of(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def option(value: object, index: int) -> QuestionOption | None:
    if not isinstance(value, dict):
        return None
    data = cast(dict[str, object], value)
    label = text_of(data.get("label"))
    if not label:
        return None
    return QuestionOption(
        id=OPTION_IDS[index],
        label=label,
        description=text_of(data.get("description")),
        recommended=data.get("recommended") is True,
    )


def question(value: object, number: int) -> Question | None:
    """One checked question numbered `q<number>`, or None when the model's entry cannot be used."""
    if not isinstance(value, dict):
        return None
    data = cast(dict[str, object], value)
    text = text_of(data.get("text"))
    kind = data.get("kind")
    raw = data.get("options")
    if not text or kind not in ("confirm", "single", "multi") or not isinstance(raw, list):
        return None
    entries = cast(list[object], raw)
    options = [found for index, item in enumerate(entries[:MAX_OPTIONS]) if (found := option(item, index))]
    if len(options) < MIN_OPTIONS:
        return None
    other = data.get("allow_other") is True and kind != "confirm"
    return Question(id=f"q{number}", text=text, kind=kind, options=options, allow_other=other)


def parse(answer: str) -> list[Question]:
    """The usable questions of the reply, at most four, in order; raises `ClarifyUnreadableError` when it has none."""
    value = json_value(answer, "{", "}")
    if not isinstance(value, dict):
        raise ClarifyUnreadableError("the reply holds no JSON object")
    raw = cast(dict[str, object], value).get("questions")
    if not isinstance(raw, list):
        raise ClarifyUnreadableError("the reply has no question list")
    found: list[Question] = []
    for item in cast(list[object], raw):
        checked = question(item, len(found) + 1)
        if checked is not None:
            found.append(checked)
        if len(found) == MAX_QUESTIONS:
            break
    return found


async def clarify(
    brief: str, plan: str, initial: Sequence[Hit], llm: LLM, *, effort: Effort, today: str
) -> list[Question]:
    """One call; the questions it wrote. Raises on a failed call or an unreadable reply."""
    completion = await llm.complete(messages(brief, plan, initial, today), max_tokens=MAX_TOKENS, effort=effort)
    return parse(completion.text)


def recommended(question: Question, answer: Answer) -> bool:
    """Whether the answer is exactly the question's recommendation."""
    return answer.other is None and sorted(answer.option_ids) == sorted(question.recommended_ids())


def changed(questions: Sequence[Question], answers: Sequence[Answer]) -> bool:
    """Whether any answer differs from its question's recommendation."""
    by_id = {answer.question_id: answer for answer in answers}
    return any((answer := by_id.get(item.id)) is None or not recommended(item, answer) for item in questions)


def clarifications(questions: Sequence[Question], answers: Sequence[Answer]) -> list[Clarification]:
    by_id = {answer.question_id: answer for answer in answers}
    return [
        Clarification(question=item.text, answer=answer_text(item, by_id[item.id]))
        for item in questions
        if item.id in by_id
    ]


def clarified_query(query: str, found: Sequence[Clarification]) -> str:
    """The query with a "Clarifications:" block listing the answers."""
    if not found:
        return query
    lines = "\n".join(f"- {item.question} {item.answer}" for item in found)
    return f"{query}\n\n{CLARIFICATIONS}\n{lines}"

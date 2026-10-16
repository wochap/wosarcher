"""Run questions in the client: the text card, the interactive prompt, `wosarcher questions`, and `wosarcher continue`.

A run started with `--clarify` or `--interactive` pauses with questions. In a terminal the command prints each
pause as text and posts the answers; without one it prints the pause as JSON on standard error and keeps waiting,
so an agent can answer with `wosarcher continue`.
"""

import json
import os
import sys
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Annotated

import typer
from rich.console import Console

from wosarcher.cli.api import Api, api, detail
from wosarcher.cli.options import JsonOption, fail
from wosarcher.models import (
    Answer,
    ContinueRequest,
    InputNeededData,
    OpenPause,
    Question,
    QuestionsPatch,
    recommended_answers,
)

Read = Callable[[str], str]
Write = Callable[[str], None]
OTHER = "o"


MAX_TIMEOUT = 3600


def question_flags(clarify: bool, interactive: bool, timeout: int | None) -> QuestionsPatch:
    """What a client run asks: nothing unless a flag says so.

    Without `--input-timeout` a run that asks waits as long as the server's `max_wait` allows, because the
    client has no presence to report; a run that asks nothing gets 0.
    """
    asking = clarify or interactive
    wait = timeout if timeout is not None else MAX_TIMEOUT if asking else 0
    return QuestionsPatch(clarify=clarify, rounds=interactive, timeout=wait)


def title(data: InputNeededData | OpenPause) -> str:
    where = "before searching" if data.kind == "clarify" else f"after round {data.after}"
    return f"The run has questions ({where})"


def options_lines(question: Question) -> list[str]:
    lines: list[str] = []
    for number, option in enumerate(question.options, start=1):
        mark = " (recommended)" if option.recommended else ""
        detail = f" — {option.description}" if option.description else ""
        lines.append(f"  {number}) {option.label}{mark}{detail}")
    if question.allow_other:
        lines.append(f"  {OTHER}) other: …")
    return lines


def header(data: InputNeededData | OpenPause) -> str:
    context = f"\n{data.context}" if data.context else ""
    return f"{title(data)}{context}"


def card(data: InputNeededData | OpenPause) -> str:
    """The whole pause as text."""
    total = len(data.questions)
    blocks = [header(data)]
    for number, question in enumerate(data.questions, start=1):
        blocks.append("\n".join([f"{number}/{total} {question.text}", *options_lines(question)]))
    return "\n\n".join(blocks)


def parse_reply(question: Question, text: str) -> Answer | None:
    """The answer a prompt reply gives: numbers (comma-separated for `multi`), `o <text>`, or Enter for the
    recommendation. None when the reply is not valid."""
    reply = text.strip()
    if not reply:
        return Answer(question_id=question.id, option_ids=question.recommended_ids())
    if question.allow_other and (reply == OTHER or reply.startswith(f"{OTHER} ")):
        other = reply[len(OTHER) :].strip()
        return Answer(question_id=question.id, other=other) if other else None
    picked: list[str] = []
    for part in reply.split(","):
        part = part.strip()
        if not part.isdigit() or not 1 <= int(part) <= len(question.options):
            return None
        picked.append(question.options[int(part) - 1].id)
    if question.kind != "multi" and len(picked) != 1:
        return None
    return Answer(question_id=question.id, option_ids=list(dict.fromkeys(picked)))


def prompt(data: InputNeededData | OpenPause, read: Read = input, write: Write = typer.echo) -> list[Answer]:
    """Ask each question at a prompt until the reply is valid; Enter takes the recommendation."""
    write(header(data))
    total = len(data.questions)
    answers: list[Answer] = []
    for number, question in enumerate(data.questions, start=1):
        write("\n".join(["", f"{number}/{total} {question.text}", *options_lines(question)]))
        while True:
            found = parse_reply(question, read("> "))
            if found is not None:
                answers.append(found)
                break
            write("Type an option number, o <text>, or press Enter for the recommendation.")
    return answers


def posted(client: Api, run_id: str, pause_id: int, answers: list[Answer]) -> bool:
    body = ContinueRequest(pause_id=pause_id, answers=answers).model_dump(mode="json")
    return client.request("POST", f"/api/runs/{run_id}/continue", json=body).is_success


class Questioner:
    """Shows a pause to the user, or to an agent as JSON on standard error."""

    def __init__(
        self, terminal: bool | None = None, paused: Callable[[], AbstractContextManager[None]] | None = None
    ) -> None:
        self.terminal = sys.stdin.isatty() if terminal is None else terminal
        self.paused = paused or nullcontext
        """Wraps a prompt, so a live progress display does not overwrite it."""

    def __call__(self, client: Api, run_id: str, data: InputNeededData) -> None:
        if not self.terminal:
            document = {"run_id": run_id, "pause": json.loads(data.model_dump_json())}
            Console(stderr=True).print(json.dumps(document, ensure_ascii=False), markup=False, highlight=False)
            return
        with self.paused():
            answers = prompt(data, input, lambda text: typer.echo(text, err=True))
        posted(client, run_id, data.pause_id, answers)


def open_pause(client: Api, run_id: str) -> OpenPause:
    response = client.request("GET", f"/api/runs/{run_id}/questions")
    if response.status_code == 409 or (response.status_code == 404 and "not_waiting" in response.text):
        raise fail("not waiting", 1)
    if not response.is_success:
        raise fail(detail(response), 2)
    return OpenPause.model_validate(response.json())


def questions(
    run_id: Annotated[str, typer.Argument(help="The run to ask about.")],
    as_json: JsonOption = False,
) -> None:
    """Print the open questions of a waiting run."""
    pause = open_pause(api(os.environ), run_id)
    typer.echo(pause.model_dump_json(indent=2) if as_json else card(pause))


def answer_option(question: Question, value: str) -> Answer:
    """`VALUE` of an `--answer`: an option ID, option IDs joined by commas, or `other:<text>`."""
    if value.startswith("other:"):
        return Answer(question_id=question.id, other=value.removeprefix("other:"))
    return Answer(question_id=question.id, option_ids=[part.strip() for part in value.split(",") if part.strip()])


def continue_(
    run_id: Annotated[str, typer.Argument(help="The waiting run.")],
    answer: Annotated[
        list[str] | None,
        typer.Option("--answer", metavar="QID=VALUE", help="An answer: option ID, a,b, or other:TEXT."),
    ] = None,
    recommended: Annotated[
        bool, typer.Option("--recommended", help="Answer every question with its recommendation.")
    ] = False,
) -> None:
    """Answer the open questions of a waiting run."""
    client = api(os.environ)
    pause = open_pause(client, run_id)
    by_question = {item.id: item for item in pause.questions}
    given: dict[str, Answer] = {}
    for spec in answer or []:
        qid, sep, value = spec.partition("=")
        if not sep or qid not in by_question:
            raise fail(f"--answer {spec}: expected QID=VALUE with QID one of {', '.join(by_question)}", 2)
        given[qid] = answer_option(by_question[qid], value)
    if recommended:
        given = {**{item.question_id: item for item in recommended_answers(pause.questions)}, **given}
    body = ContinueRequest(pause_id=pause.pause_id, answers=list(given.values())).model_dump(mode="json")
    response = client.request("POST", f"/api/runs/{run_id}/continue", json=body)
    if response.status_code == 409:
        raise fail("not waiting", 1)
    if not response.is_success:
        raise fail(detail(response), 2)
    typer.echo(f"run {run_id}: continued")

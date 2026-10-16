"""The text card, the prompt, and the `--answer` values of `wosarcher questions` and `wosarcher continue`."""

from datetime import UTC, datetime

from typer.testing import CliRunner

from tests.conftest import Daemon
from wosarcher.cli import app
from wosarcher.cli.questions import answer_option, card, parse_reply, prompt, question_flags
from wosarcher.models import Answer, InputNeededData, Question, QuestionOption

runner = CliRunner()


def option(letter: str, label: str, recommended: bool = False) -> QuestionOption:
    return QuestionOption(id=letter, label=label, recommended=recommended)


def pause() -> InputNeededData:
    queries = Question(
        id="q1",
        text="Search these next?",
        kind="multi",
        options=[option("a", "lithium price", True), option("b", "cobalt supply", True), option("c", "again", True)],
        allow_other=True,
    )
    stop = Question(
        id="q2",
        text="Stop research here and write?",
        kind="confirm",
        options=[option("a", "No, keep going", True), option("b", "Yes, write now")],
    )
    return InputNeededData(
        pause_id=1,
        kind="round",
        after=1,
        context="More on prices.",
        questions=[queries, stop],
        created=datetime(2026, 1, 1, tzinfo=UTC),
        timeout=60,
        max_wait=1800,
    )


def test_card() -> None:
    text = card(pause())
    assert "after round 1" in text
    assert "More on prices." in text
    assert "1/2 Search these next?" in text
    assert "  1) lithium price (recommended)" in text
    assert "  o) other: …" in text
    assert "2/2 Stop research here and write?" in text
    assert "  2) Yes, write now" in text
    assert "o)" not in text.split("2/2")[1]


def test_reply_numbers_other_and_enter() -> None:
    found = pause()
    multi, confirm = found.questions
    assert parse_reply(multi, "") == Answer(question_id="q1", option_ids=["a", "b", "c"])
    assert parse_reply(multi, "1,3") == Answer(question_id="q1", option_ids=["a", "c"])
    assert parse_reply(multi, "o SUNAT 2026") == Answer(question_id="q1", other="SUNAT 2026")
    assert parse_reply(multi, "o") is None
    assert parse_reply(multi, "9") is None
    assert parse_reply(confirm, "2") == Answer(question_id="q2", option_ids=["b"])
    assert parse_reply(confirm, "1,2") is None
    assert parse_reply(confirm, "o text") is None


def test_prompt_repeats_until_valid() -> None:
    replies = iter(
        [
            "x",
            "1,3",
            "",
        ]
    )
    shown: list[str] = []
    answers = prompt(pause(), lambda _: next(replies), shown.append)
    assert answers == [
        Answer(question_id="q1", option_ids=["a", "c"]),
        Answer(question_id="q2", option_ids=["a"]),
    ]
    assert any("Type an option number" in line for line in shown)


def test_answer_values() -> None:
    multi = pause().questions[0]
    assert answer_option(multi, "a") == Answer(question_id="q1", option_ids=["a"])
    assert answer_option(multi, "a,c") == Answer(question_id="q1", option_ids=["a", "c"])
    assert answer_option(multi, "other:Diario Oficial") == Answer(question_id="q1", other="Diario Oficial")


def test_question_flags() -> None:
    nothing = question_flags(False, False, None)
    assert (nothing.clarify, nothing.rounds, nothing.timeout) == (False, False, 0)
    asking = question_flags(True, True, 120)
    assert (asking.clarify, asking.rounds, asking.timeout) == (True, True, 120)
    default_wait = question_flags(False, True, None)
    assert (default_wait.clarify, default_wait.rounds, default_wait.timeout) == (False, True, 3600)


def test_not_waiting(daemon: Daemon) -> None:
    from tests.conftest import create_run
    from tests.test_cli_run import summary, wait_until

    run_id = create_run(daemon, "q")
    wait_until(lambda: summary(daemon, run_id)["status"] == "done")
    shown = runner.invoke(app, ["questions", run_id])
    assert shown.exit_code == 1
    assert "not waiting" in shown.stderr
    cont = runner.invoke(app, ["continue", run_id, "--recommended"])
    assert cont.exit_code == 1


def test_invalid_answer_exits_2(daemon: Daemon) -> None:
    from tests.conftest import create_run
    from tests.test_cli_run import summary, wait_until

    run_id = create_run(daemon, "ask")
    wait_until(lambda: summary(daemon, run_id)["status"] == "waiting")
    missing = runner.invoke(app, ["continue", run_id, "--answer", "q1=a"])
    assert missing.exit_code == 2
    assert "q2" in missing.stderr
    unknown = runner.invoke(app, ["continue", run_id, "--answer", "q9=a"])
    assert unknown.exit_code == 2
    ok = runner.invoke(app, ["continue", run_id, "--answer", "q1=a", "--answer", "q2=other:SUNAT"])
    assert ok.exit_code == 0, ok.output

"""Options and checks shared by the `wosarcher` client and the `wosarcherd` engine commands."""

from typing import Annotated, get_args

import typer
from rich.console import Console

from wosarcher.models import STAGES, Effort, Sources, Stage, domain_list, search_language

FORMATS = ("report", "answer")


def fail(error: Exception | str, code: int = 1) -> typer.Exit:
    Console(stderr=True, soft_wrap=True).print(f"error: {error}", markup=False, highlight=False)
    return typer.Exit(code)


def stage_option(value: str | None) -> Stage | None:
    if value is None:
        return None
    if value not in STAGES:
        raise fail(f"unknown stage '{value}'; valid stages: {', '.join(STAGES)}", 2)
    return value


def sources_option(sources: str, attach: list[str] | None) -> Sources:
    if sources not in get_args(Sources):
        raise fail(f"--sources must be one of: {', '.join(get_args(Sources))}", 2)
    if sources == "files" and not attach:
        raise fail("--sources files needs --attach", 2)
    return sources  # pyright: ignore[reportReturnType]  (checked above)


def format_option(value: str | None) -> str | None:
    if value is None or value in FORMATS:
        return value
    raise typer.BadParameter(f"must be one of: {', '.join(FORMATS)}")


def token_budget(value: str | None) -> str | None:
    """A positive integer or `auto`, for the token budget flags."""
    if value is None or value == "auto" or (value.isdigit() and int(value) > 0):
        return value
    raise typer.BadParameter("must be a positive integer or 'auto'")


def language_option(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return search_language(value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None


def domains_option(value: list[str] | None) -> list[str] | None:
    if not value:
        return value
    try:
        return domain_list(value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None


def effort_option(value: str | None) -> str | None:
    if value is None or value in get_args(Effort):
        return value
    raise typer.BadParameter(f"must be one of: {', '.join(get_args(Effort))}")


def thinking(step: str) -> object:
    return typer.Option(
        f"--{step}-thinking",
        metavar="LEVEL",
        callback=effort_option,
        help=f"Thinking for the {step} step: {', '.join(get_args(Effort))}.",
    )


ProfileOption = Annotated[str | None, typer.Option("--profile", help="Profile to use for this command.")]
SetOption = Annotated[list[str] | None, typer.Option("--set", help="Override one field: dotted.key=value.")]
AttachOption = Annotated[list[str] | None, typer.Option("--attach", help="File, directory, or glob to attach.")]
SourcesOption = Annotated[str, typer.Option("--sources", help="files, web, or both.")]
UntilOption = Annotated[str | None, typer.Option("--until", help=f"Stop after this stage: {', '.join(STAGES)}.")]
FromOption = Annotated[str, typer.Option("--from", help=f"First stage to run again: {', '.join(STAGES)}.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON document when the run ends.")]
ToneOption = Annotated[str | None, typer.Option("--tone", help="Writing tone.")]
ToneInstructionsOption = Annotated[str | None, typer.Option("--tone-instructions", help="Extra tone instructions.")]
WordsOption = Annotated[int | None, typer.Option("--words", help="Target report length in words.")]
LanguageOption = Annotated[str | None, typer.Option("--language", help="Report language.")]
MarkerOption = Annotated[str | None, typer.Option("--citation-marker", help="numeric, superscript, or author-year.")]
StyleOption = Annotated[str | None, typer.Option("--reference-style", help="APA, MLA, Chicago, or IEEE.")]
FormatOption = Annotated[
    str | None,
    typer.Option("--format", metavar="report|answer", callback=format_option, help="Write a report or an answer."),
]
DepthOption = Annotated[str | None, typer.Option("--depth", help="Depth preset; see `wosarcher depth list`.")]
SubQueriesOption = Annotated[int | None, typer.Option("--sub-queries", min=1, help="Sub-queries to plan.")]
ResultsOption = Annotated[int | None, typer.Option("--results-per-query", min=1, help="Search results per query.")]
PagesOption = Annotated[int | None, typer.Option("--max-pages", min=1, help="Pages to fetch at most.")]
PassagesOption = Annotated[int | None, typer.Option("--passages-per-query", min=1, help="Passages kept per query.")]
ContextTokensOption = Annotated[
    str | None,
    typer.Option("--context-tokens", metavar="N|auto", callback=token_budget, help="Context token cap."),
]
GapContextTokensOption = Annotated[
    str | None,
    typer.Option(
        "--gap-context-tokens", metavar="N|auto", callback=token_budget, help="Gap step context token budget."
    ),
]
RoundsOption = Annotated[int | None, typer.Option("--rounds", min=1, max=8, help="Research rounds.")]
QueriesPerRoundOption = Annotated[
    int | None, typer.Option("--queries-per-round", min=1, help="Follow-up queries per round at most.")
]
SearchLanguageOption = Annotated[
    str | None,
    typer.Option(
        "--search-language", metavar="CODE", callback=language_option, help="Search language: all, auto, or a code."
    ),
]
AllowDomainOption = Annotated[
    list[str] | None,
    typer.Option(
        "--allow-domain",
        metavar="DOMAIN",
        callback=domains_option,
        help="Only use search results from this domain (repeatable).",
    ),
]
BlockDomainOption = Annotated[
    list[str] | None,
    typer.Option(
        "--block-domain",
        metavar="DOMAIN",
        callback=domains_option,
        help="Drop search results from this domain (repeatable).",
    ),
]
ModelOption = Annotated[str | None, typer.Option("--model", help="Chat model for this run (llm.model).")]
PlanThinkingOption = Annotated[str | None, thinking("plan")]
GapThinkingOption = Annotated[str | None, thinking("gap")]
WriteThinkingOption = Annotated[str | None, thinking("write")]

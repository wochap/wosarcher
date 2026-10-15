"""`wosarcher catalog "<brief>"` and `wosarcher catalog draft "<brief>"`, through the daemon's API.

`catalog` starts a catalog run with `POST /api/runs` (`kind` `catalog`), follows
it like `wosarcher run`, and prints the `records` array of `catalog.json`, or the
report for `--output report|both` (with `--json`, the whole file plus a `report`
key when one was written). `catalog draft` posts the brief to
`POST /api/catalog/draft` and prints the derived structure, ready for
`--structure`.

The structure flags apply over the `--structure` file; seeds and leaf types from
flags replace the file's lists. With flags and no file, the structure gets the
fields `id` (slug), `name` (required text), `type` (enum of the seed and leaf
types), `parent_id` (ref), and `website` (url).

Exit status: as `wosarcher run`; `catalog draft` exits 1 when the draft call fails.
"""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, cast, get_args

import typer
from pydantic import ValidationError

from wosarcher.cli.api import api, detail
from wosarcher.cli.options import (
    AllowDomainOption,
    AttachOption,
    BlockDomainOption,
    ClientProfileOption,
    ContextWindowOption,
    DraftThinkingOption,
    ExtractThinkingOption,
    FormatOption,
    LanguageOption,
    MarkerOption,
    MaxOutputOption,
    ModelOption,
    SearchLanguageOption,
    SetOption,
    StyleOption,
    ToneInstructionsOption,
    ToneOption,
    UseOption,
    WordsOption,
    fail,
    language_option,
    use_map,
)
from wosarcher.cli.run import created, llm_patch, uploads, watch, writing_patch
from wosarcher.models import (
    CATALOG_STAGES,
    CatalogOutput,
    DomainPatch,
    DraftCreate,
    ExpandMode,
    RunCreate,
    Stage,
    Structure,
    catalog_writes,
)

DRAFT = "draft"
DRAFT_TIMEOUT_SECONDS = 600.0
SOURCES = ("web", "both")


def seed_option(value: str) -> dict[str, Any]:
    """`NAME|TYPE[|URL]` as a structure seed."""
    parts = [part.strip() for part in value.split("|")]
    if len(parts) not in (2, 3) or not parts[0] or not parts[1]:
        raise fail(f"--seed '{value}' must look like NAME|TYPE or NAME|TYPE|URL", 2)
    seed: dict[str, Any] = {"name": parts[0], "type": parts[1]}
    if len(parts) == 3 and parts[2]:
        seed["url"] = parts[2]
    return seed


def default_fields(types: list[str]) -> list[dict[str, Any]]:
    return [
        {"name": "id", "type": "slug"},
        {"name": "name", "type": "text", "required": True},
        {"name": "type", "type": "enum", "values": types},
        {"name": "parent_id", "type": "ref"},
        {"name": "website", "type": "url"},
    ]


def read_structure(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise fail(f"--structure {path}: {error}", 2) from None
    if not isinstance(data, dict):
        raise fail(f"--structure {path}: must hold a JSON object", 2)
    return cast(dict[str, Any], data)


def structure_request(
    path: str | None,
    seeds: list[str],
    relation: str | None,
    leaves: list[str],
    expand: str | None,
    limits: dict[str, int | None],
    output: str | None = None,
) -> dict[str, Any] | None:
    """The file with the flags over it; None when neither is given (the `draft` stage derives one)."""
    given = {name: value for name, value in limits.items() if value is not None}
    flagged = bool(seeds or relation is not None or leaves or expand is not None or given or output is not None)
    if path is None and not flagged:
        return None
    data = read_structure(path) if path is not None else {}
    parsed = [seed_option(seed) for seed in seeds]
    if path is None:
        missing = [flag for flag, value in (("--seed", seeds), ("--relation", relation)) if not value]
        if missing:
            raise fail(f"a structure from flags needs {' and '.join(missing)} (or --structure FILE)", 2)
    if seeds:
        data["seeds"] = parsed
    if relation is not None:
        data["relation"] = relation
    if leaves:
        data["leaf_types"] = leaves
    if expand is not None:
        data["expand"] = expand
    if output is not None:
        data["output"] = output
    if given:
        data["limits"] = {**cast(dict[str, Any], data.get("limits") or {}), **given}
    if path is None:
        types = list(dict.fromkeys([*(seed["type"] for seed in data["seeds"]), *leaves]))
        data["fields"] = default_fields(types)
    try:
        Structure.model_validate(data)
    except ValidationError as error:
        raise fail(f"structure: {error}", 2) from None
    return data


def expand_option(value: str | None) -> str | None:
    if value is None or value in get_args(ExpandMode):
        return value
    raise typer.BadParameter(f"must be one of: {', '.join(get_args(ExpandMode))}")


def output_option(value: str | None) -> str | None:
    if value is None or value in get_args(CatalogOutput):
        return value
    raise typer.BadParameter(f"must be one of: {', '.join(get_args(CatalogOutput))}")


def check_writing(found: dict[str, Any] | None, writing: Mapping[str, object]) -> None:
    """Writing flags need a report: fail naming the first one and `--output` when the output is `table`."""
    given = [flag for flag, value in writing.items() if value is not None]
    if not given or found is None:
        return
    if not catalog_writes(Structure.model_validate(found)):
        raise fail(f"{given[0]}: writes a report; pass --output report or --output both", 2)


def until_option(value: str | None) -> Stage | None:
    if value is None:
        return None
    for stage in CATALOG_STAGES:
        if stage == value:
            return stage
    raise fail(f"--until {value} is not a catalog stage; stages: {', '.join(CATALOG_STAGES)}", 2)


def draft(
    brief: str,
    attach: list[str],
    profile: str | None,
    use: list[str] | None,
    request_llm: dict[str, Any],
) -> None:
    """Post the brief to `POST /api/catalog/draft` and print the structure."""
    try:
        body = DraftCreate(brief=brief, profile=profile, use=use_map(use), **request_llm)
    except ValidationError as error:
        raise fail(error, 2) from None
    files = [("request", (None, body.model_dump_json(exclude_defaults=True).encode())), *uploads(attach)]
    response = api(os.environ).request("POST", "/api/catalog/draft", files=files, timeout=DRAFT_TIMEOUT_SECONDS)
    if not response.is_success:
        raise fail(detail(response), 2 if response.status_code < 500 else 1)
    typer.echo(json.dumps(response.json(), indent=2, ensure_ascii=False))


CATALOG_ONLY = (
    "--structure",
    "--seed",
    "--relation",
    "--leaf",
    "--expand",
    "--output",
    "--max-depth",
    "--max-nodes",
    "--pages-per-node",
    "--search-language",
    "--record-language",
    "--allow-domain",
    "--block-domain",
    "--sources",
    "--set",
    "--until",
    "--json",
    "--tone",
    "--tone-instructions",
    "--words",
    "--language",
    "--citation-marker",
    "--reference-style",
    "--format",
)


def catalog(
    words: Annotated[
        list[str], typer.Argument(metavar="[draft] BRIEF", help="The brief; `draft BRIEF` prints a structure.")
    ],
    structure: Annotated[str | None, typer.Option("--structure", metavar="FILE", help="A JSON structure file.")] = None,
    seed: Annotated[
        list[str] | None, typer.Option("--seed", metavar="NAME|TYPE[|URL]", help="A seed entity (repeatable).")
    ] = None,
    relation: Annotated[str | None, typer.Option("--relation", help="The child relation, such as 'adscritos'.")] = None,
    leaf: Annotated[list[str] | None, typer.Option("--leaf", metavar="TYPE", help="A leaf type (repeatable).")] = None,
    expand: Annotated[
        str | None,
        typer.Option("--expand", metavar="links|search|both", callback=expand_option, help="How children are found."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option(
            "--output", metavar="table|report|both", callback=output_option, help="Records, a report, or both."
        ),
    ] = None,
    max_depth: Annotated[int | None, typer.Option("--max-depth", min=1, max=10, help="Deepest node level.")] = None,
    max_nodes: Annotated[int | None, typer.Option("--max-nodes", min=1, max=5000, help="Nodes at most.")] = None,
    pages_per_node: Annotated[
        int | None, typer.Option("--pages-per-node", min=1, max=10, help="Pages fetched per node.")
    ] = None,
    search_language: SearchLanguageOption = None,
    record_language: Annotated[
        str | None,
        typer.Option(
            "--record-language", metavar="CODE", callback=language_option, help="Language of the records' text values."
        ),
    ] = None,
    allow_domain: AllowDomainOption = None,
    block_domain: BlockDomainOption = None,
    attach: AttachOption = None,
    sources: Annotated[str, typer.Option("--sources", help="web or both.")] = "both",
    profile: ClientProfileOption = None,
    use: UseOption = None,
    model: ModelOption = None,
    draft_thinking: DraftThinkingOption = None,
    extract_thinking: ExtractThinkingOption = None,
    context_window: ContextWindowOption = None,
    max_output: MaxOutputOption = None,
    tone: ToneOption = None,
    tone_instructions: ToneInstructionsOption = None,
    length: WordsOption = None,
    language: LanguageOption = None,
    citation_marker: MarkerOption = None,
    reference_style: StyleOption = None,
    format_: FormatOption = None,
    set_: SetOption = None,
    until: Annotated[
        str | None, typer.Option("--until", help=f"Stop after this stage: {', '.join(CATALOG_STAGES)}.")
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the whole catalog.json (with the report) when the run ends.")
    ] = False,
) -> None:
    """Crawl BRIEF into a catalog of records on the daemon; `catalog draft BRIEF` prints a structure to edit."""
    llm = llm_patch(
        model, {"draft": draft_thinking, "extract": extract_thinking}, (context_window, max_output), (None, None)
    )
    writing = {
        "--tone": tone,
        "--tone-instructions": tone_instructions,
        "--words": length,
        "--language": language,
        "--citation-marker": citation_marker,
        "--reference-style": reference_style,
        "--format": format_,
    }
    if words[:1] == [DRAFT] and len(words) == 2:
        catalog_flags = {
            "--structure": structure,
            "--seed": seed,
            "--relation": relation,
            "--leaf": leaf,
            "--expand": expand,
            "--output": output,
            "--max-depth": max_depth,
            "--max-nodes": max_nodes,
            "--pages-per-node": pages_per_node,
            "--search-language": search_language,
            "--record-language": record_language,
            "--allow-domain": allow_domain,
            "--block-domain": block_domain,
            "--sources": None if sources == "both" else sources,
            "--set": set_,
            "--until": until,
            "--json": as_json or None,
            **writing,
        }
        given = [flag for flag in CATALOG_ONLY if catalog_flags[flag]]
        if given:
            raise fail(f"{', '.join(given)}: not for catalog draft", 2)
        draft(words[1], attach or [], profile, use, {"llm": llm})
        return
    if len(words) != 1:
        raise fail("give one BRIEF (quote it), or draft BRIEF", 2)
    if sources not in SOURCES:
        raise fail(f"--sources must be one of: {', '.join(SOURCES)}", 2)
    stop = until_option(until)
    limits = {"max_depth": max_depth, "max_nodes": max_nodes, "pages_per_node": pages_per_node}
    found = structure_request(structure, seed or [], relation, leaf or [], expand, limits, output)
    check_writing(found, writing)
    languages = {"language": search_language, "record_language": record_language}
    given_languages = {key: value for key, value in languages.items() if value is not None}
    extra_set = list(set_ or [])
    if found is not None:
        found.update(given_languages)
    else:
        extra_set += [f"catalog.{key}={json.dumps(value)}" for key, value in given_languages.items()]
        if search_language is not None:
            extra_set.append(f"search.language={json.dumps(search_language)}")
    try:
        request = RunCreate.model_validate(
            {
                "query": words[0],
                "kind": "catalog",
                "structure": found,
                "sources": sources,
                "until": stop,
                "profile": profile,
                "use": use_map(use),
                "domains": DomainPatch(allow=allow_domain or None, block=block_domain or None),
                "llm": llm,
                "writing": writing_patch(
                    tone=tone,
                    tone_instructions=tone_instructions,
                    words=length,
                    language=language,
                    citation_marker=citation_marker,
                    reference_style=reference_style,
                    format=format_,
                ),
                "set": extra_set,
            }
        )
    except ValidationError as error:
        raise fail(error, 2) from None
    files = uploads(attach or [])
    client = api(os.environ)
    body = [("request", (None, request.model_dump_json(exclude_unset=True).encode())), *files]
    run = created(client, "/api/runs", files=body)
    watch(client, run, 1, as_json, early_exit=2, kind="catalog")

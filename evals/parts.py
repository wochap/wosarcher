"""Question parts: the distinct things a query asks for, asked once per parent run and cached.

`<DIR>/parts.jsonl` holds one line per parent run ID; later judge calls,
`--force` included, reuse it. Delete the file to ask again.
"""

import json
import re
from pathlib import Path
from string import Template

from pydantic import BaseModel, TypeAdapter

from wosarcher.models import Message
from wosarcher.ports import LLM

PROMPT = Path(__file__).parent / "prompts" / "parts.md"
MAX_PARTS = 20
MAX_TOKENS = 1024
STRINGS = TypeAdapter(list[str])
FENCE = re.compile(r"^\s*```[A-Za-z]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


class Parts(BaseModel):
    """One line of `parts.jsonl`."""

    parent_run_id: str
    query: str
    parts: list[str]


def parse_parts(text: str) -> list[str] | None:
    """The answer's list of non-blank strings, optionally fenced, first `MAX_PARTS` kept; None when empty or invalid."""
    fenced = FENCE.match(text)
    try:
        found = STRINGS.validate_python(json.loads(fenced.group(1) if fenced else text), strict=True)
    except ValueError:
        return None
    parts = [part.strip() for part in found if part.strip()][:MAX_PARTS]
    return parts or None


def read_parts(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        return {}
    records = [Parts.model_validate_json(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
    return {record.parent_run_id: record.parts for record in records}


def save_parts(path: Path, parent_run_id: str, query: str, parts: list[str]) -> None:
    with path.open("a", encoding="utf-8") as out:
        out.write(Parts(parent_run_id=parent_run_id, query=query, parts=parts).model_dump_json() + "\n")


async def question_parts(llm: LLM, query: str) -> list[str] | None:
    """One call with the query rendered into the parts template; the parsed parts or None."""
    system = Template(PROMPT.read_text(encoding="utf-8")).substitute(query=query)
    completion = await llm.complete(
        [Message(role="user", content=system)], max_tokens=MAX_TOKENS, effort="none", temperature=0
    )
    return parse_parts(completion.text)

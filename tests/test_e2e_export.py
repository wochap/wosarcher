"""Report export with the real pandoc adapter on the recorded fixture run; skipped without pandoc and typst."""

import asyncio
import re
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from tests.fixtures.recorded import copy_fixture
from wosarcher.adapters.pandoc import PandocExporter
from wosarcher.document import document
from wosarcher.models import Report, RunRecord
from wosarcher.store import RunStore

pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None or shutil.which("typst") is None, reason="pandoc and typst are not on PATH"
)

# An en dash between two dollar amounts, which a math reader would take as a formula.
PRICE = "costs $0.50\u2013$2 per page [4]"
EXTRA = (
    "\nHosting "
    + PRICE
    + """, and both studies agree<sup>1,2</sup>.

| Plan | Price |
|---|---|
| Free | S/ 0.00 [13] |

```{=typst}
#str(6*7)
```

<sup>note</sup> ![diagram](/etc/passwd)
"""
)


def docx_text(data: bytes) -> str:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return xml


def text_of(xml: str) -> str:
    return re.sub(r"<[^>]+>", "", xml)


def pdf_text(data: bytes, tmp_path: Path) -> str | None:
    if shutil.which("pdftotext") is None:
        return None
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(data)
    out = tmp_path / "out.txt"
    asyncio.run(_run("pdftotext", str(pdf), str(out)))
    return out.read_text(encoding="utf-8")


async def _run(*args: str) -> None:
    process = await asyncio.create_subprocess_exec(*args)
    await process.wait()


def fixture(tmp_path: Path, query: str | None = None, prefix: str = "", extra: str = EXTRA) -> tuple[RunRecord, Report]:
    store = RunStore(tmp_path / "runs", tmp_path / "cache")
    run_id = copy_fixture(tmp_path / "runs")
    record = store.read_record(run_id)
    report = store.read_artifact(run_id, "report.json", Report)
    head, _, references = report.markdown.partition("\n## References")
    report = report.model_copy(update={"markdown": prefix + head + extra + "\n## References" + references})
    if query is not None:
        record = record.model_copy(update={"request": record.request.model_copy(update={"query": query})})
    return record, report


def export(record: RunRecord, report: Report, fmt: str) -> bytes:
    return asyncio.run(PandocExporter().export(document(record, report), fmt))  # pyright: ignore[reportArgumentType]


def test_fixture_run_pdf_and_docx(tmp_path: Path) -> None:
    record, report = fixture(tmp_path)
    pdf = export(record, report, "pdf")
    assert pdf.startswith(b"%PDF")
    xml = docx_text(export(record, report, "docx"))
    text = text_of(xml)
    assert "battery recycling" in text
    assert "2026-10-05 · 20260101-000000-fixture" in text
    assert "Question" not in text
    assert "[1]" in text
    assert "S/ 0.00 [13]" in text
    assert "References" in text
    assert "<w:tbl>" in xml
    assert PRICE in text
    assert 'w:val="superscript"' in xml
    assert "<sup>1,2</sup>" not in text
    assert "&lt;sup&gt;note&lt;/sup&gt;" in xml
    assert "#str(6*7)" in text
    assert "diagram" in text
    assert "passwd" not in text
    printed = pdf_text(pdf, tmp_path)
    if printed is not None:
        assert "#str(6*7)" in printed
        assert "\n42\n" not in printed
        assert PRICE in printed
        assert "passwd" not in printed


def test_report_with_its_own_title(tmp_path: Path) -> None:
    record, report = fixture(tmp_path, prefix="# Arma hoy tu sistema de alertas\n\n", extra="")
    text = text_of(docx_text(export(record, report, "docx")))
    assert text.count("Arma hoy tu sistema de alertas") == 1
    assert text.index("Arma hoy") < text.index("20260101-000000-fixture") < text.index("Question")
    assert text.index("Question") < text.index("battery recycling") < text.index("References")
    assert export(record, report, "pdf").startswith(b"%PDF")


def test_short_query_without_title(tmp_path: Path) -> None:
    record, report = fixture(tmp_path, query="What is SINOE?", extra="")
    text = text_of(docx_text(export(record, report, "docx")))
    assert text.strip().startswith("What is SINOE?")
    assert "Question" not in text


def test_long_research_brief(tmp_path: Path) -> None:
    first = " ".join(["Assess"] + ["regional"] * 42)[:300]
    brief = first + "\n\n" + "\n".join(f"- point {n} " + "x" * 60 for n in range(55))
    assert len(first) == 300
    assert len(brief) > 4000
    record, report = fixture(tmp_path, query=brief, extra="")
    markdown = document(record, report)
    title = markdown.splitlines()[0].removeprefix("# ")
    assert title.endswith("…")
    assert len(title) <= 120
    assert first.startswith(title[:-1])
    assert "## Question\n\n> Assess" in markdown
    assert "> - point 54 " in markdown
    text = text_of(docx_text(export(record, report, "docx")))
    assert text.index("Question") < text.index("point 54") < text.index("Battery recycling")
    assert export(record, report, "pdf").startswith(b"%PDF")

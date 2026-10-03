from wosarcher.models import Attachment
from wosarcher.stages.load import load, outline


def test_invalid_bytes_replaced() -> None:
    result = load([Attachment(name="a.md", data=b"caf\xff")])
    assert result.pages[0].text == "caf�"


def test_title_from_first_h1_or_name() -> None:
    result = load([Attachment(name="a.md", data=b"intro\n\n# Battery notes\n"), Attachment(name="b.txt", data=b"x")])
    assert [page.source.title for page in result.pages] == ["Battery notes", "b.txt"]
    assert all(page.source.kind == "file" for page in result.pages)


def test_same_content_twice() -> None:
    result = load([Attachment(name="a.md", data=b"same"), Attachment(name="copy/a.md", data=b"same")])
    assert [page.source.uri for page in result.pages] == ["a.md"]
    assert [(s.item, s.reason) for s in result.skipped] == [("copy/a.md", "duplicate of a.md")]


def test_pdf_ingest_detected() -> None:
    result = load(
        [Attachment(name="a.md", data=b"<!-- page: 3 -->\n<!-- a: p3-b2 -->\ntext"), Attachment(name="b.md", data=b"t")]
    )
    assert [page.format for page in result.pages] == ["pdf-ingest", "markdown"]


def test_outline_two_lines_per_heading() -> None:
    text = b"# Intro\none\ntwo\nthree\n\n# Method\nfour\n\nfive\nsix\n"
    page = load([Attachment(name="a.md", data=text)]).pages[0]
    result = outline(page)
    assert "# Intro\none\ntwo\n# Method\nfour\nfive" in result
    assert "three" not in result
    assert "six" not in result


def test_outline_cut() -> None:
    page = load([Attachment(name="a.md", data=("# H\n" + "x " * 3000).encode())]).pages[0]
    assert len(outline(page)) == 2000

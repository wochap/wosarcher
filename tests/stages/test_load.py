from wosarcher.models import Attachment
from wosarcher.stages.chunk import sections
from wosarcher.stages.load import load, outline, render_json


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


def test_json_dataset_of_nodes() -> None:
    data = (
        '{"nodes": [{"id": "sac", "name": "Sociedad Anónima Cerrada",'
        ' "costs": [{"concept": "Minuta", "amount_pen": null}]}], "edges": []}'
    )
    result = load([Attachment(name="empresa_peru.json", data=data.encode())])
    page = result.pages[0]
    assert (page.format, page.source.title) == ("json", "empresa_peru.json")
    assert page.text == (
        "## nodes\n\n### Sociedad Anónima Cerrada\n\nid: sac\nname: Sociedad Anónima Cerrada\ncosts:\n\n"
        "#### Item 1\n\nconcept: Minuta\namount_pen: null\n\n## edges\n"
    )


def test_json_top_level_array_and_scalars() -> None:
    assert render_json([{"title": "A"}, {"x": 1}]) == "## A\n\ntitle: A\n\n## Item 2\n\nx: 1\n"
    assert render_json({"k": [1, "x", True], "s": "v"}) == "## k\n\n- 1\n- x\n- true\n\n## s\n\nv\n"
    assert render_json(3) == "3\n"


def test_json_deep_nesting_cut() -> None:
    text = render_json({"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": 1}}}}}}}})
    assert text.splitlines()[-1] == '          g: {"h":1}'


def test_json_broken_skipped() -> None:
    result = load([Attachment(name="data.json", data=b'{"a": }'), Attachment(name="b.md", data=b"x")])
    assert [page.source.uri for page in result.pages] == ["b.md"]
    assert result.skipped[0].item == "data.json"
    assert result.skipped[0].reason.startswith("invalid JSON: Expecting value: line 1 column 7")


def test_json_headings_become_heading_paths() -> None:
    page = load([Attachment(name="d.json", data=b'{"nodes": [{"name": "A", "v": 1}]}')]).pages[0]
    assert [section.path for section in sections(page.text)] == [("nodes",), ("nodes", "A")]

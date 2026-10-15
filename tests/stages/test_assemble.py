from tests.stages.catalog_data import structure
from wosarcher.models import CatalogRecord, ExtractedRecord, Node, WaveEntry
from wosarcher.stages.assemble import assemble, normalised_name, slug, stop_note, unique_slug

URL = "https://mef.test"


def build(nodes: list[Node], records: list[ExtractedRecord]) -> CatalogRecord:
    return assemble(structure(), nodes, records, waves=[WaveEntry(wave=1)], reason="frontier empty", note="n")


def test_assembled_record() -> None:
    node = Node(
        id="mef", name="MEF", type="ministry", parent_id="poder-ejecutivo", depth=1, status="extracted", flags=["f1"]
    )
    record = ExtractedRecord(
        node_id="mef",
        record={"name": "Ministerio de Economía", "head_name": None, "verified_on": None, "website": URL},
        sources={"website": URL},
        flags=["f2"],
    )
    catalog = build([node], [record])
    assert catalog.records == [
        {
            "id": "mef",
            "name": "Ministerio de Economía",
            "type": "ministry",
            "parent_id": "poder-ejecutivo",
            "head_name": None,
            "verified_on": None,
            "website": URL,
            "sources": {"website": URL},
            "flags": ["f1", "f2"],
        }
    ]
    assert catalog.by_type == {"ministry": 1}
    assert catalog.by_depth == {"1": 1}
    assert CatalogRecord.model_validate_json(catalog.model_dump_json()) == catalog


def test_slug_collision() -> None:
    taken: set[str] = set()
    assert [unique_slug("Secretaría General", taken) for _ in range(2)] == [
        "secretaria-general",
        "secretaria-general-2",
    ]
    assert slug("  ¿Qué?  ") == "que"
    assert normalised_name("Instituto  Nacional, de Estadística!") == "instituto nacional de estadistica"


def test_required_missing() -> None:
    node = Node(id="x", name="X", type="agency", status="extracted")
    catalog = build([node], [ExtractedRecord(node_id="x", record={"name": None})])
    assert catalog.records == []
    assert [(item.node_id, item.field) for item in catalog.dropped] == [("x", "name")]


def test_fill_counts_and_unextracted_nodes() -> None:
    nodes = [Node(id=f"n{n}", name=f"N{n}", type="agency", status="extracted") for n in range(5)]
    nodes.append(Node(id="failed", name="F", type="agency", status="failed"))
    records = [
        ExtractedRecord(node_id=f"n{n}", record={"name": f"N{n}", "website": URL if n < 2 else None}) for n in range(5)
    ]
    catalog = build(nodes, records)
    assert catalog.fill["website"] == 2
    assert catalog.fill["name"] == 5
    assert catalog.fill["id"] == 5
    assert catalog.nodes == 6
    assert len(catalog.records) == 5


def test_stop_note() -> None:
    nodes = [Node(id="a", name="A", type="power")]
    note = stop_note("frontier empty", wave=5, structure=structure(), nodes=nodes, max_pages=40)
    assert note == "No unexpanded nodes left after wave 5. Max depth 3 was not reached."
    deep = [Node(id="a", name="A", type="power", depth=3)]
    assert stop_note("page limit reached", wave=4, structure=structure(), nodes=deep, max_pages=400) == (
        "Page limit 400 reached."
    )

from tests.stages.catalog_data import structure
from wosarcher.models import Node
from wosarcher.stages.expand import expand

PCM = "Presidencia del Consejo de Ministros"


def node(**fields: object) -> Node:
    return Node.model_validate({"id": "pcm", "name": PCM, "type": "ministry", **fields})


def texts(mode: str, item: Node) -> list[tuple[str, str]]:
    result = expand([(3, item)], structure(expand=mode), 2)
    return [(query.id, query.text) for query in result.queries]


def test_url_and_both() -> None:
    item = node(url="https://pcm.test")
    result = expand([(3, item)], structure(), 2)
    assert result.nodes[0].url == "https://pcm.test"
    assert [(q.id, q.text, q.round, q.node_id) for q in result.queries] == [
        ("n3c", f"{PCM} organismos adscritos", 2, "pcm")
    ]


def test_no_url_and_links() -> None:
    assert texts("links", node()) == [("n3s", f"{PCM} ministry")]


def test_no_url_and_search() -> None:
    assert texts("search", node()) == [("n3s", f"{PCM} ministry"), ("n3c", f"{PCM} organismos adscritos")]


def test_url_and_links_has_no_query() -> None:
    assert texts("links", node(url="https://pcm.test")) == []


def test_leaf_node() -> None:
    assert texts("both", node(type="office")) == [("n3s", f"{PCM} office")]


def test_max_depth_node() -> None:
    assert texts("both", node(depth=3, url="https://pcm.test")) == []

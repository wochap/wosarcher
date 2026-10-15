"""Expand: per node of a wave, the URL to fetch first, a self query, and a children query.

A self query (`n<k>s`, "<name> <type>") is written only for a node with no
URL; a children query (`n<k>c`, "<name> <relation>") only for an expandable
node when the expand mode is `search` or `both`. `k` is the node's discovery
index (1-based position in `nodes.jsonl`).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from wosarcher.models import Node, Query, Structure, node_children_query_id, node_self_query_id
from wosarcher.stages.search import cut


@dataclass(frozen=True)
class NodeExpansion:
    node_id: str
    index: int
    url: str | None
    """The URL to fetch first, when known."""
    queries: list[Query] = field(default_factory=list[Query])


@dataclass(frozen=True)
class ExpandResult:
    nodes: list[NodeExpansion]

    @property
    def queries(self) -> list[Query]:
        return [query for item in self.nodes for query in item.queries]


def expand(nodes: Sequence[tuple[int, Node]], structure: Structure, wave: int) -> ExpandResult:
    """`nodes`: the wave's nodes with their discovery index."""
    found: list[NodeExpansion] = []
    for index, node in nodes:
        queries: list[Query] = []
        if node.url is None:
            text = cut(f"{node.name} {node.type}")
            queries.append(Query(id=node_self_query_id(index), text=text, round=wave, node_id=node.id))
        if structure.expand != "links" and structure.is_expandable(node.type, node.depth):
            text = cut(f"{node.name} {structure.relation}")
            queries.append(Query(id=node_children_query_id(index), text=text, round=wave, node_id=node.id))
        found.append(NodeExpansion(node_id=node.id, index=index, url=node.url, queries=queries))
    return ExpandResult(nodes=found)

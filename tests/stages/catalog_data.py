"""A small catalog structure shared by the catalog stage and runner tests."""

from typing import Any

from wosarcher.models import Structure

TYPES = ["power", "ministry", "agency", "office"]


def structure_data(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "fields": [
            {"name": "id", "type": "slug"},
            {"name": "name", "type": "text", "required": True},
            {"name": "type", "type": "enum", "values": TYPES},
            {"name": "parent_id", "type": "ref"},
            {"name": "head_name", "type": "text", "volatile": True, "dated_by": "verified_on"},
            {"name": "verified_on", "type": "date"},
            {"name": "website", "type": "url"},
        ],
        "relation": "organismos adscritos",
        "seeds": [{"name": "Poder Ejecutivo", "type": "power", "url": "https://pe.test"}],
        "leaf_types": ["office"],
        "expand": "both",
        "limits": {"max_depth": 3, "max_nodes": 200, "pages_per_node": 2},
    }
    data.update(changes)
    return data


def structure(**changes: Any) -> Structure:
    return Structure.model_validate(structure_data(**changes))

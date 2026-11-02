"""Construct native metadata and handles for the maintained Skill example."""

import ast
import json
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


def node(path, identifier, values, x, y):
    """Return native node metadata for one actual component and supplied values."""
    code = path.read_text(encoding="utf-8")
    template, _ = build_custom_component_template(Component(_code=code))
    component_type = next(
        item.name
        for item in ast.parse(code).body
        if isinstance(item, ast.ClassDef)
        and any(
            isinstance(base, ast.Name) and base.id in {"Component", "AgentComponent"}
            for base in item.bases
        )
    )
    for name, value in values.items():
        template["template"][name]["value"] = value
    return {
        "id": identifier,
        "type": "genericNode",
        "position": {"x": x, "y": y},
        "data": {"id": identifier, "type": component_type, "node": template},
    }


def edge(source, name, target, field):
    """Connect declared output/input metadata without inventing handle types."""
    output = next(
        item for item in source["data"]["node"]["outputs"] if item["name"] == name
    )
    input_field = target["data"]["node"]["template"][field]
    outgoing = {
        "dataType": source["data"]["type"],
        "id": source["id"],
        "name": name,
        "output_types": output["types"],
    }
    incoming = {
        "fieldName": field,
        "id": target["id"],
        "inputTypes": input_field.get("input_types", []),
        "type": input_field["type"],
    }
    return {
        "id": source["id"] + "-" + name + "-" + target["id"] + "-" + field,
        "source": source["id"],
        "target": target["id"],
        "sourceHandle": json.dumps(outgoing),
        "targetHandle": json.dumps(incoming),
        "data": {"sourceHandle": outgoing, "targetHandle": incoming},
    }
